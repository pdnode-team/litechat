"""Shared ownership checks so ticket 404s do not leak whether a row exists."""

from typing import Optional

from litestar.exceptions import NotFoundException, PermissionDeniedException

from app.models.ticket import Ticket
from app.models.user import User

STAFF_ROLES = ("agent", "admin")


def require_ticket_view(user: User, ticket: Optional[Ticket]) -> Ticket:
    """Return the ticket if the caller may see it; otherwise a uniform 404."""
    if ticket is None:
        raise NotFoundException("Ticket not found.")
    if user.role == "customer" and ticket.customer_id != user.id:
        raise NotFoundException("Ticket not found.")
    return ticket


def require_staff(user: User, detail: str = "Forbidden: Only support staff can perform this action.") -> None:
    if user.role not in STAFF_ROLES:
        raise PermissionDeniedException(detail)
