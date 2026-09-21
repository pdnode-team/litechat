from datetime import datetime
from typing import Optional, List
from pydantic import ConfigDict, BaseModel, Field

from app.services.form_logic import MAX_DESCRIPTION_LENGTH

class AttachmentItem(BaseModel):
    name: str = Field(max_length=255)
    url: str = Field(max_length=500)
    file_type: str = Field(max_length=40)
    size: int = Field(ge=0)

class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    message_type: str = "text"  # text, whisper, action_card
    attachments: Optional[List[AttachmentItem]] = None

class MessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_id: Optional[int] = None
    sender_name: str
    sender_role: str
    message_type: str
    content: str
    attachments: Optional[List[AttachmentItem]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
