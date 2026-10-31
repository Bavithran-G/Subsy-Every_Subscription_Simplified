from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import user_out
from app.api.util import Paging, page, paginate
from app.core.db import get_db
from app.core.deps import admin_only
from app.core.security import hash_password, validate_password
from app.models import Role, User
from app.schemas.common import Page, StaffCreateIn, UserOut, UserUpdateIn
from app.services.common import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(role: str | None = None, q: str | None = None, paging: Paging = Depends(),
               _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    if role:
        stmt = stmt.where(User.role == Role(role))
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    rows, total = paginate(db, stmt, paging)
    return page([user_out(u) for u in rows], total, paging)


@router.post("/staff", response_model=UserOut, status_code=201)
def create_staff(data: StaffCreateIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Only an administrator can add internal staff (PS requirement)."""
    err = validate_password(data.password)
    if err:
        raise HTTPException(422, err)
    email = data.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists")
    u = User(email=email, full_name=data.full_name, password_hash=hash_password(data.password), role=Role.staff)
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    audit(db, admin.id, "user.create_staff", "user", u.id, email=email)
    db.commit()
    return user_out(u)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdateIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if data.is_active is not None:
        if u.id == admin.id and not data.is_active:
            raise HTTPException(400, "You cannot deactivate your own account")
        if u.is_active and not data.is_active:
            u.token_version += 1
        u.is_active = data.is_active
    if data.full_name:
        u.full_name = data.full_name
    audit(db, admin.id, "user.update", "user", u.id, **data.model_dump(exclude_none=True))
    db.commit()
    return user_out(u)
