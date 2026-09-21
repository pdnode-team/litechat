from typing import Optional
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="customer", nullable=False)  # customer, agent, admin
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Advisory flag: an unverified address still logs in, it only surfaces a
    # banner prompting the user to confirm their email.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Bumped on password change/reset and deactivation so outstanding JWTs die.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Set while an email-change token is outstanding; applied on confirmation.
    pending_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
