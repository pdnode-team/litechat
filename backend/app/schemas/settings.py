from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmailSettingsUpdate(BaseModel):
    """SMTP configuration. Omitted fields are left unchanged.

    Send an empty string to clear a value; ``smtp_password`` is write-only and
    is never echoed back by the API.
    """

    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    smtp_username: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = Field(default=None, max_length=255)
    smtp_use_tls: Optional[bool] = None
    smtp_from: Optional[str] = Field(default=None, max_length=255)
    public_app_url: Optional[str] = Field(default=None, max_length=255)


class NotificationSettingsUpdate(BaseModel):
    notify_new_ticket: Optional[bool] = None
    notify_ticket_reply: Optional[bool] = None
    notify_assignment: Optional[bool] = None
    notify_status_change: Optional[bool] = None
    support_email: Optional[str] = Field(default=None, max_length=255)


class TestEmailRequest(BaseModel):
    to: EmailStr


class TestEmailResult(BaseModel):
    sent: bool
    detail: str
