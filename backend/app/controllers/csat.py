from typing import Annotated, Optional
from litestar import Controller, get, post, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, ValidationException
from litestar.params import PathParameter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.csat_rating import CSATRating
from app.schemas.csat import CSATCreate, CSATResponse
from app.controllers.auth import get_current_user_from_request
from app.services.access import require_ticket_view
from app.services import events as event_bus
from app.services.events import CSAT_SUBMITTED, Event


def _csat_event(ticket: Ticket, score: int) -> Event:
    """A rating changes the analytics and the ticket's satisfaction badge."""
    return Event(
        type=CSAT_SUBMITTED,
        notification={
            "ticket_id": ticket.id,
            "ticket_code": ticket.ticket_code,
            "score": score,
            "customer_id": ticket.customer_id,
            "assigned_agent_id": ticket.assigned_agent_id,
        },
        ticket_id=ticket.id,
        user_ids=[ticket.customer_id] + ([ticket.assigned_agent_id] if ticket.assigned_agent_id else []),
        staff=True,
    )

class CSATController(Controller):
    path = "/api/tickets/{ticket_id:int}/csat"

    @get("/")
    async def get_csat(self, request: Request, ticket_id: Annotated[int, PathParameter()]) -> Optional[CSATResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required")

        async with async_session_factory() as session:
            require_ticket_view(current_user, await session.get(Ticket, ticket_id))

            stmt = select(CSATRating).where(CSATRating.ticket_id == ticket_id)
            rating = (await session.execute(stmt)).scalar_one_or_none()
            if not rating:
                return None
            return CSATResponse.model_validate(rating)

    @post("/")
    async def submit_csat(self, request: Request, ticket_id: Annotated[int, PathParameter()], data: CSATCreate) -> CSATResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required")

        if current_user.role in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Support staff cannot submit customer satisfaction ratings.")

        if data.score < 1 or data.score > 5:
            raise ValidationException("CSAT rating score must be between 1 and 5.")

        async with async_session_factory() as session:
            ticket = require_ticket_view(current_user, await session.get(Ticket, ticket_id))

            if ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You can only rate your own tickets.")

            if ticket.status not in ("resolved", "closed"):
                raise ValidationException("CSAT rating can only be submitted for resolved or closed tickets.")

            stmt = select(CSATRating).where(CSATRating.ticket_id == ticket_id)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                raise ValidationException("A rating has already been submitted for this ticket.")

            rating = CSATRating(
                ticket_id=ticket_id,
                customer_id=ticket.customer_id,
                score=data.score,
                comment=data.comment,
            )
            session.add(rating)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValidationException("A rating has already been submitted for this ticket.") from None
            await session.refresh(rating)
            await event_bus.publish(_csat_event(ticket, rating.score))
            return CSATResponse.model_validate(rating)

