from typing import Dict, List, Any, Optional
from pydantic import BaseModel

class AgentPerformanceItem(BaseModel):
    agent_id: int
    name: str
    assigned_count: int
    resolved_count: int
    avg_resolution_time_minutes: float
    csat_avg: Optional[float] = None

class AnalyticsSummaryResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    pending_tickets: int
    in_progress_tickets: int
    resolved_tickets: int
    closed_tickets: int
    
    sla_compliance_rate: Optional[float] = None
    sla_breached_count: int
    
    csat_average_score: Optional[float] = None
    csat_total_reviews: int
    
    category_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]
    
    agents_performance: List[AgentPerformanceItem]
