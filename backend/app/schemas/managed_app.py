from datetime import datetime
from typing import Optional
from pydantic import ConfigDict, BaseModel

class ManagedAppCreate(BaseModel):
    name: str
    code: str
    base_url: Optional[str] = None
    is_active: bool = True

class ManagedAppUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None

class ManagedAppResponse(BaseModel):
    id: int
    name: str
    code: str
    base_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
