from datetime import datetime
from typing import Optional
from pydantic import ConfigDict, BaseModel, Field

# Bounds mirror the columns in app/models/canned_response.py; exceeding one is a
# StringDataRightTruncation (an opaque 500) on PostgreSQL.
MAX_SHORTCUT_LENGTH = 50
MAX_TITLE_LENGTH = 150
MAX_CATEGORY_LENGTH = 100

class CannedResponseCreate(BaseModel):
    shortcut: str = Field(min_length=1, max_length=MAX_SHORTCUT_LENGTH)
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str = Field(min_length=1)
    category: str = Field(default="general", max_length=MAX_CATEGORY_LENGTH)

class CannedResponseUpdate(BaseModel):
    shortcut: Optional[str] = Field(default=None, min_length=1, max_length=MAX_SHORTCUT_LENGTH)
    title: Optional[str] = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    content: Optional[str] = Field(default=None, min_length=1)
    category: Optional[str] = Field(default=None, max_length=MAX_CATEGORY_LENGTH)

class CannedResponseResponse(BaseModel):
    id: int
    shortcut: str
    title: str
    content: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
