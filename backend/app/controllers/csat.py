from typing import Annotated, Optional
from litestar import Controller, get, post, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException, ValidationException
from litestar.params import PathParameter
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.csat_rating import CSATRating
from app.schemas.csat import CSATCreate, CSATResponse
from app.controllers.auth import get_current_user_from_request

class CSATController(Controller):
    path = "/api/tickets/{ticket_id:int}/csat"

    @get("/")
    async def get_csat(self, request: Request, ticket_id: Annotated[int, PathParameter()]) -> Optional[CSATResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found")

            # Ownership check: Customer can only view CSAT of their own tickets
            if current_user.role == "customer" and ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You do not have permission to access CSAT for this ticket.")

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
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found")

            if ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You can only rate your own tickets.")

            if ticket.status not in ("resolved", "closed"):
                raise ValidationException("CSAT rating can only be submitted for resolved or closed tickets.")

            stmt = select(CSATRating).where(CSATRating.ticket_id == ticket_id)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                existing.score = data.score
                existing.comment = data.comment
                await session.commit()
                await session.refresh(existing)
                return CSATResponse.model_validate(existing)

            rating = CSATRating(
                ticket_id=ticket_id,
                customer_id=ticket.customer_id,
                score=data.score,
                comment=data.comment,
            )
            session.add(rating)
            await session.commit()
            await session.refresh(rating)
            return CSATResponse.model_validate(rating)

