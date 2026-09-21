from datetime import timedelta
from typing import Optional, Dict, Any

import jwt
import bcrypt

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, WS_TICKET_TTL_MINUTES
from app.db.base import utcnow

# bcrypt silently truncates past this; reject instead of storing a prefix.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(raw, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        raw = plain_password.encode("utf-8")
        if len(raw) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "typ": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_ws_ticket(user_id: int, token_version: int) -> str:
    """Short-lived JWT for the WebSocket query string so access tokens stay out of logs."""
    expire = utcnow() + timedelta(minutes=WS_TICKET_TTL_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "ver": token_version, "typ": "ws", "exp": expire},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def access_token_claims(user_id: int, role: str, name: str, token_version: int) -> Dict[str, Any]:
    return {
        "sub": str(user_id),
        "role": role,
        "name": name,
        "ver": token_version,
    }
