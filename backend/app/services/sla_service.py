from datetime import datetime, timedelta
from typing import Tuple, Optional
from app.config import SLA_FIRST_RESPONSE_MINUTES, SLA_RESOLUTION_MINUTES

def calculate_sla_deadlines(priority: str, start_time: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    start = start_time or datetime.utcnow()
    first_resp_mins = SLA_FIRST_RESPONSE_MINUTES.get(priority.lower(), SLA_FIRST_RESPONSE_MINUTES["medium"])
    resolution_mins = SLA_RESOLUTION_MINUTES.get(priority.lower(), SLA_RESOLUTION_MINUTES["medium"])
    
    first_resp_due = start + timedelta(minutes=first_resp_mins)
    resolution_due = start + timedelta(minutes=resolution_mins)
    
    return first_resp_due, resolution_due

def get_sla_status(
    due_at: Optional[datetime],
    completed_at: Optional[datetime] = None,
) -> str:
    """
    Returns: 'fulfilled', 'breached', 'on_track'
    """
    if not due_at:
        return "on_track"
    
    now = datetime.utcnow()
    if completed_at:
        return "fulfilled" if completed_at <= due_at else "breached"
    
    if now > due_at:
        return "breached"
    
    return "on_track"
