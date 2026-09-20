from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UTCDateTime, utcnow

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"), index=True, nullable=False)
    
    sender_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(50), nullable=False)  # customer, agent, admin, bot, system
    
    # Message type: text, whisper (internal note), system (event), action_card
    message_type: Mapped[str] = mapped_column(String(50), default="text", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # JSON string representing list of {name, url, type, size}
    attachments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
