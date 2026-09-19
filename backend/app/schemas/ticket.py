from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import ConfigDict, BaseModel, Field
from app.schemas.auth import UserResponse
from app.schemas.managed_app import ManagedAppResponse
from app.schemas.ticket_type import TicketTypeResponse

class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=5)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    category: Literal["technical", "billing", "account", "general"] = "general"
    tags: Optional[str] = ""
    app_id: Optional[int] = None
    target_url: Optional[str] = None
    ticket_type_id: Optional[int] = None
    custom_fields: Optional[Dict[str, Any]] = None

class TicketStatusUpdateRequest(BaseModel):
    status: Literal["open", "pending", "in_progress", "resolved", "closed"]

class TicketAssignRequest(BaseModel):
    agent_id: Optional[int] = None

class TicketPriorityUpdateRequest(BaseModel):
    priority: Literal["low", "medium", "high", "urgent"]

class TicketUpdateRequest(BaseModel):
    """Partial edit of the ticket's descriptive fields.

    Status/priority/assignment have dedicated endpoints with their own rules.
    """

    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, min_length=5)
    category: Optional[Literal["technical", "billing", "account", "general"]] = None
    tags: Optional[str] = None
    target_url: Optional[str] = None

class TicketResponse(BaseModel):
    id: int
    ticket_code: str
    title: str
    description: str
    status: str
    priority: str
    category: str
    customer_id: int
    assigned_agent_id: Optional[int] = None
    customer: Optional[UserResponse] = None
    assigned_agent: Optional[UserResponse] = None

    # App & Dynamic Ticket Type
    app_id: Optional[int] = None
    app: Optional[ManagedAppResponse] = None
    target_url: Optional[str] = None
    ticket_type_id: Optional[int] = None
    ticket_type: Optional[TicketTypeResponse] = None
    custom_fields: Optional[Dict[str, Any]] = None
    
    first_response_due_at: Optional[datetime] = None
    resolution_due_at: Optional[datetime] = None
    first_responded_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    sla_first_response_status: Optional[str] = None # on_track, breached, fulfilled
    sla_resolution_status: Optional[str] = None     # on_track, breached, fulfilled
    
    tags: Optional[str] = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
