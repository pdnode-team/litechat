from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class CannedResponseCreate(BaseModel):
    shortcut: str
    title: str
    content: str
    category: str = "general"

class CannedResponseUpdate(BaseModel):
    shortcut: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None

class CannedResponseResponse(BaseModel):
    id: int
    shortcut: str
    title: str
    content: str
    category: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
