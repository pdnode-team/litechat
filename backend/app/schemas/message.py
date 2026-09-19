from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class AttachmentItem(BaseModel):
    name: str
    url: str
    file_type: str
    size: int

class MessageCreate(BaseModel):
    content: str
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

    class Config:
        from_attributes = True
