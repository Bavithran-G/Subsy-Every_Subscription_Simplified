import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

PASSWORD_RULES = (
    "Password must be more than 8 characters and contain an uppercase letter, "
    "a lowercase letter and a special character."
)


def validate_password(password: str) -> str | None:
    """Return an error message, or None when the password meets the PS rules."""
    if len(password) <= 8:
        return PASSWORD_RULES
    if not re.search(r"[A-Z]", password):
        return PASSWORD_RULES
    if not re.search(r"[a-z]", password):
        return PASSWORD_RULES
    if not re.search(r"[^A-Za-z0-9]", password):
        return PASSWORD_RULES
    if len(password.encode()) > 72:
        return "Password must be at most 72 bytes."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, token_version: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])


def new_reset_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
