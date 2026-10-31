from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token, hash_password, hash_token, new_reset_token, validate_password, verify_password,
)
from app.models import Customer, PasswordResetToken, Role, User
from app.models.base import utcnow
from app.schemas.common import (
    ChangePasswordIn, ForgotIn, LoginIn, Msg, RegisterIn, ResetIn, TokenOut, UserOut,
)
from app.services.common import audit, send_email

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: User) -> UserOut:
    out = UserOut.model_validate(u)
    out.customer_id = u.customer.id if u.customer else None
    return out


def _token(u: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(u.id, str(u.role), u.token_version), user=user_out(u))


def _check_password(pw: str):
    err = validate_password(pw)
    if err:
        raise HTTPException(422, err)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    _check_password(data.password)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(data.password), full_name=data.full_name,
                role=Role.customer)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    # link to an existing customer record created by staff, or create one
    customer = db.scalars(select(Customer).where(func.lower(Customer.email) == email)).first()
    if customer:
        if customer.user_id:
            db.rollback()
            raise HTTPException(409, "An account with this email already exists")
        customer.user_id = user.id
    else:
        customer = Customer(name=data.full_name, email=email, company=data.company, phone=data.phone,
                            user_id=user.id)
        db.add(customer)
    audit(db, user.id, "auth.register", "user", user.id)
    db.commit()
    db.refresh(user)
    return _token(user)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(func.lower(User.email) == data.email.lower())).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated")
    user.last_login_at = utcnow()
    db.commit()
    return _token(user)


@router.post("/logout", response_model=Msg)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version += 1  # revokes every token issued so far
    db.commit()
    return Msg(message="Signed out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/forgot-password", response_model=Msg)
def forgot_password(data: ForgotIn, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalars(select(User).where(func.lower(User.email) == data.email.lower())).first()
    if user and user.is_active:
        raw, hashed = new_reset_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=hashed,
                                  expires_at=utcnow() + timedelta(minutes=s.reset_token_minutes)))
        link = f"{s.frontend_url}/reset-password?token={raw}"
        send_email(db, user.email, "Reset your Subsy password",
                   f"Hello {user.full_name},\n\nUse this link within {s.reset_token_minutes} minutes to reset "
                   f"your password:\n{link}\n\nIf you didn't request this, ignore this email.")
        audit(db, user.id, "auth.reset_requested", "user", user.id)
        db.commit()
    # identical response whether or not the account exists (no account enumeration)
    delivery = "smtp" if s.smtp_host else "outbox"
    return Msg(message="If an account exists for that email, a password reset link has been issued.",
               detail={"email_delivery": delivery})


@router.post("/reset-password", response_model=Msg)
def reset_password(data: ResetIn, db: Session = Depends(get_db)):
    _check_password(data.password)
    tok = db.scalars(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(data.token))
                     ).first()
    if not tok or tok.used_at or tok.expires_at < utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired")
    user = db.get(User, tok.user_id)
    user.password_hash = hash_password(data.password)
    user.token_version += 1
    tok.used_at = utcnow()
    # invalidate any other outstanding tokens for this user
    for other in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                             PasswordResetToken.used_at.is_(None))):
        other.used_at = utcnow()
    audit(db, user.id, "auth.reset_completed", "user", user.id)
    db.commit()
    return Msg(message="Password updated. You can now sign in.")


@router.post("/change-password", response_model=TokenOut)
def change_password(data: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    _check_password(data.new_password)
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    db.commit()
    return _token(user)
