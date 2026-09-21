from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FileUpload(Base, TimestampMixin):
    """A file stored under UPLOAD_DIR, owned by the user who uploaded it."""

    __tablename__ = "file_uploads"

    stored_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploader_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
