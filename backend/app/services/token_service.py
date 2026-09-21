"""Single-use expiring tokens for password reset and email verification."""
import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PASSWORD_RESET_TTL_MINUTES, EMAIL_VERIFICATION_TTL_MINUTES
from app.db.base import utcnow
from app.models.auth_token import (
    PURPOSE_EMAIL_CHANGE,
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    AuthToken,
)

TTL_BY_PURPOSE = {
    PURPOSE_PASSWORD_RESET: PASSWORD_RESET_TTL_MINUTES,
    PURPOSE_EMAIL_VERIFICATION: EMAIL_VERIFICATION_TTL_MINUTES,
    PURPOSE_EMAIL_CHANGE: EMAIL_VERIFICATION_TTL_MINUTES,
}


def hash_token(raw_token: str) -> str:
    """Hash a token for storage. SHA-256 is enough: the token is 256 bits of entropy."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_token() -> Tuple[str, str]:
    """Return (raw_token, token_hash). Only the hash is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


async def issue_token(session: AsyncSession, user_id: int, purpose: str) -> str:
    """Invalidate previous tokens of this purpose and issue a fresh one."""
    if purpose not in TTL_BY_PURPOSE:
        raise ValueError(f"Unknown token purpose: {purpose}")

    existing = (
        await session.execute(
            select(AuthToken).where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
        )
    ).scalars().all()
    now = utcnow()
    for token in existing:
        # Superseded: mark as used so only the newest link works.
        token.used_at = now

    raw_token, token_hash = generate_token()
    session.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=TTL_BY_PURPOSE[purpose]),
        )
    )
    await session.commit()
    return raw_token


async def consume_token(session: AsyncSession, raw_token: str, purpose: str) -> Optional[AuthToken]:
    """Return the matching usable token and mark it used, or None if invalid.

    Unknown, expired, already-used and wrong-purpose tokens are all rejected the
    same way so a caller cannot probe which tokens exist.
    """
    if not raw_token:
        return None

    token = (
        await session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == hash_token(raw_token),
                AuthToken.purpose == purpose,
            )
        )
    ).scalar_one_or_none()

    if token is None or not token.is_usable:
        return None

    token.used_at = utcnow()
    await session.flush()
    return token
