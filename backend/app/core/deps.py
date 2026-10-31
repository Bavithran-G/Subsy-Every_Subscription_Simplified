from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import Role, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from None
    user = db.get(User, int(payload["sub"]))
    # role and revocation are re-checked against the database on every request — the token's role claim is
    # never trusted on its own
    if not user or not user.is_active or user.token_version != payload.get("tv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid")
    return user


def require(*roles: Role) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user
    return checker


admin_only = require(Role.admin)
internal = require(Role.admin, Role.staff)
any_user = get_current_user
