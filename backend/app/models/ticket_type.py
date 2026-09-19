from typing import Optional
from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin

class TicketType(Base, TimestampMixin):
    __tablename__ = "ticket_types"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # JSON array of field schemas: [{ key, label, type, required, placeholder, options }]
    fields_schema_json: Mapped[Optional[str]] = mapped_column(Text, default="[]", nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
