from typing import Optional
from sqlalchemy import String, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin

class FaqItem(Base, TimestampMixin):
    __tablename__ = "faq_items"

    category: Mapped[str] = mapped_column(String(50), default="general", index=True, nullable=False)
    question: Mapped[str] = mapped_column(String(255), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[Optional[str]] = mapped_column(String(255), default="", nullable=True)
    # JSON array of drill-down quick options/prompts: ["option1", "option2"]
    quick_replies_json: Mapped[Optional[str]] = mapped_column(Text, default="[]", nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
