from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UTCDateTime

class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    ticket_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status: open, pending, in_progress, resolved, closed
    status: Mapped[str] = mapped_column(String(50), default="open", index=True, nullable=False)
    
    # Priority: low, medium, high, urgent
    priority: Mapped[str] = mapped_column(String(50), default="medium", index=True, nullable=False)
    
    # Category: technical, billing, account, general
    category: Mapped[str] = mapped_column(String(100), default="general", index=True, nullable=False)
    
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_agent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # App / Website & Dynamic Ticket Type
    app_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("managed_apps.id"), nullable=True)
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ticket_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ticket_types.id"), nullable=True)
    custom_fields_json: Mapped[Optional[str]] = mapped_column(Text, default="{}", nullable=True)

    # SLA Tracking Fields
    first_response_due_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    resolution_due_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    first_responded_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    sla_first_alerted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    sla_resolution_alerted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    tags: Mapped[Optional[str]] = mapped_column(String(500), default="", nullable=True)
