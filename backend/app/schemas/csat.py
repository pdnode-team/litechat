from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CSATCreate(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: Optional[str] = None

class CSATResponse(BaseModel):
    id: int
    ticket_id: int
    customer_id: int
    score: int
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
