from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class SlaSettingsUpdate(BaseModel):
    sla_first_urgent: Optional[int] = Field(default=None, ge=1, le=10080)
    sla_first_high: Optional[int] = Field(default=None, ge=1, le=10080)
    sla_first_medium: Optional[int] = Field(default=None, ge=1, le=10080)
    sla_first_low: Optional[int] = Field(default=None, ge=1, le=10080)
    sla_resolution_urgent: Optional[int] = Field(default=None, ge=1, le=43200)
    sla_resolution_high: Optional[int] = Field(default=None, ge=1, le=43200)
    sla_resolution_medium: Optional[int] = Field(default=None, ge=1, le=43200)
    sla_resolution_low: Optional[int] = Field(default=None, ge=1, le=43200)
    sla_business_hours_enabled: Optional[bool] = None
    sla_weekdays: Optional[str] = Field(default=None, max_length=40)
    sla_start: Optional[str] = Field(default=None, max_length=5)
    sla_end: Optional[str] = Field(default=None, max_length=5)
    sla_timezone: Optional[str] = Field(default=None, max_length=64)
    sla_observe_holidays: Optional[bool] = None


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


class EmailOutboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    to_address: str
    subject: str
    kind: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    next_attempt_at: datetime
    created_at: datetime
    updated_at: datetime
