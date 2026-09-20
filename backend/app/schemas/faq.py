from datetime import datetime
from typing import Optional, List
from pydantic import ConfigDict, BaseModel, Field

# Every bound mirrors the column it is stored in (see app/models/faq_item.py).
# Without them a long value reached PostgreSQL and came back as a
# StringDataRightTruncation, i.e. an opaque 500, while SQLite accepted it happily.
MAX_CATEGORY_LENGTH = 50
MAX_QUESTION_LENGTH = 255
MAX_KEYWORDS_LENGTH = 255

class FaqItemCreate(BaseModel):
    category: str = Field(default="general", max_length=MAX_CATEGORY_LENGTH)
    question: str = Field(min_length=3, max_length=MAX_QUESTION_LENGTH)
    answer: str = Field(min_length=1)
    keywords: Optional[str] = Field(default="", max_length=MAX_KEYWORDS_LENGTH)
    quick_replies: Optional[List[str]] = []
    sort_order: int = 0
    is_active: bool = True

class FaqItemUpdate(BaseModel):
    category: Optional[str] = Field(default=None, max_length=MAX_CATEGORY_LENGTH)
    question: Optional[str] = Field(default=None, min_length=3, max_length=MAX_QUESTION_LENGTH)
    answer: Optional[str] = Field(default=None, min_length=1)
    keywords: Optional[str] = Field(default=None, max_length=MAX_KEYWORDS_LENGTH)
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
