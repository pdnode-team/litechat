from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UTCDateTime, utcnow

STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


class EmailOutbox(Base, TimestampMixin):
    """A single outbound email. The request path only inserts a row; a background
    worker delivers it so a slow or down SMTP server cannot stall the API.
    """

    __tablename__ = "email_outbox"

    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="transactional")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
