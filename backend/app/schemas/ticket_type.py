from datetime import datetime
from typing import Optional, List, Any
from pydantic import ConfigDict, BaseModel

class CustomFieldDefinition(BaseModel):
    key: str
    label: str
    type: str  # text, textarea, select, number, switch, url
    required: bool = False
    placeholder: Optional[str] = ""
    options: Optional[List[str]] = []

class TicketTypeCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = ""
    fields_schema: List[CustomFieldDefinition] = []
    is_active: bool = True

class TicketTypeUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    fields_schema: Optional[List[CustomFieldDefinition]] = None
    is_active: Optional[bool] = None

class TicketTypeResponse(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str] = ""
    fields_schema: List[CustomFieldDefinition] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
