from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Token purposes
PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_EMAIL_VERIFICATION = "email_verification"


def utcnow_naive() -> datetime:
    """Naive UTC, matching the convention used by the existing columns.

    The database columns are timezone-naive and SQLite drops tzinfo on read, so
    writing aware values would produce a mix of aware and naive datetimes.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthToken(Base):
    """Single-use, expiring token for password reset / email verification.

    Only the SHA-256 hash of the token is stored, so a database leak does not
    expose usable reset links.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    @property
    def is_expired(self) -> bool:
        return utcnow_naive() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not self.is_expired
