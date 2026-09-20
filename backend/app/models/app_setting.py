from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class AppSetting(Base):
    """Runtime-editable configuration, so administrators can change SMTP and
    notification behaviour from the UI instead of editing environment variables.

    Environment variables remain the fallback: a setting that has never been
    written to this table resolves to its environment value (or built-in default).
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Secrets are encrypted at rest and never returned by the API.
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
