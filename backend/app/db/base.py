from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Current UTC time as a **naive** datetime.

    Every DateTime column in this project stores naive UTC, and that is not a
    stylistic choice: asyncpg encodes ``timestamp without time zone`` by
    subtracting a naive epoch, so binding an aware datetime raises
    "can't subtract offset-naive and offset-aware datetimes". SQLite accepts
    aware values silently, which is why this only breaks on PostgreSQL.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UTCDateTime(TypeDecorator):
    """A DateTime column that always round-trips as naive UTC.

    Values are normalised at the driver boundary, so a stray aware datetime can
    never reach asyncpg and fail at insert time — the convention is enforced
    structurally instead of relying on every caller remembering to use
    ``utcnow()``.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
