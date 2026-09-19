from datetime import datetime
from typing import Optional, List
from pydantic import ConfigDict, BaseModel

class FaqItemCreate(BaseModel):
    category: str = "general"
    question: str
    answer: str
    keywords: Optional[str] = ""
    quick_replies: Optional[List[str]] = []
    sort_order: int = 0
    is_active: bool = True

class FaqItemUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    keywords: Optional[str] = None
    quick_replies: Optional[List[str]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class FaqItemResponse(BaseModel):
    id: int
    category: str
    question: str
    answer: str
    keywords: Optional[str] = ""
    quick_replies: Optional[List[str]] = []
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FaqQueryRequest(BaseModel):
    query: str
    category: Optional[str] = None

class FaqQueryResponse(BaseModel):
    matches: List[FaqItemResponse]
    suggested_reply: Optional[str] = None
    quick_options: List[str] = []
    can_escalate_ticket: bool = True
