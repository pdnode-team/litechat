import json
from typing import Annotated, List, Optional
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException, ValidationException
from litestar.params import PathParameter, QueryParameter
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.session import async_session_factory
from app.models.ticket_type import TicketType
from app.models.ticket import Ticket
from app.schemas.ticket_type import (
    TicketTypeCreate,
    TicketTypeUpdate,
    TicketTypeResponse,
    CustomFieldDefinition,
)
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request

def type_to_response(tt: TicketType) -> TicketTypeResponse:
    fields = []
    if tt.fields_schema_json:
        try:
            raw = json.loads(tt.fields_schema_json)
            fields = [CustomFieldDefinition(**f) for f in raw]
        except Exception:
            fields = []
    return TicketTypeResponse(
        id=tt.id,
        name=tt.name,
        code=tt.code,
        description=tt.description or "",
        fields_schema=fields,
        is_active=tt.is_active,
        created_at=tt.created_at,
        updated_at=tt.updated_at,
    )

class TicketTypeController(Controller):
    path = "/api/ticket-types"

    @get("/")
    async def list_ticket_types(
        self,
        request: Request,
        active_only: Annotated[Optional[bool], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[TicketTypeResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            filters = []
            if active_only:
                filters.append(TicketType.is_active.is_(True))

            total = (
                await session.execute(select(func.count()).select_from(TicketType).where(*filters))
            ).scalar_one()

            stmt = (
                select(TicketType)
                .where(*filters)
                .order_by(TicketType.id.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            items = [type_to_response(tt) for tt in result.scalars().all()]
            return Page[TicketTypeResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/")
    async def create_ticket_type(self, request: Request, data: TicketTypeCreate) -> TicketTypeResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage ticket types.")

        async with async_session_factory() as session:
            existing = await session.execute(select(TicketType).where(TicketType.code == data.code.strip()))
            if existing.scalar_one_or_none():
                raise ValidationException(f"Ticket type with code '{data.code}' already exists.")

            fields_json = json.dumps([f.model_dump() for f in data.fields_schema]) if data.fields_schema else "[]"
            new_type = TicketType(
                name=data.name.strip(),
                code=data.code.strip().lower(),
                description=data.description.strip() if data.description else "",
                fields_schema_json=fields_json,
                is_active=data.is_active,
            )
            session.add(new_type)
            await session.commit()
            await session.refresh(new_type)
            return type_to_response(new_type)

    @put("/{type_id:int}")
    async def update_ticket_type(self, request: Request, type_id: Annotated[int, PathParameter()], data: TicketTypeUpdate) -> TicketTypeResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage ticket types.")

        async with async_session_factory() as session:
            tt = await session.get(TicketType, type_id)
            if not tt:
                raise NotFoundException("Ticket type not found.")

            if data.name is not None:
                tt.name = data.name.strip()
            if data.code is not None:
                tt.code = data.code.strip().lower()
            if data.description is not None:
                tt.description = data.description.strip()
            if data.fields_schema is not None:
                tt.fields_schema_json = json.dumps([f.model_dump() for f in data.fields_schema])
            if data.is_active is not None:
                tt.is_active = data.is_active

            await session.commit()
            await session.refresh(tt)
            return type_to_response(tt)

    @delete("/{type_id:int}")
    async def delete_ticket_type(self, request: Request, type_id: Annotated[int, PathParameter()]) -> None:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage ticket types.")

        async with async_session_factory() as session:
            tt = await session.get(TicketType, type_id)
            if not tt:
                raise NotFoundException("Ticket type not found.")

            # Friendly pre-check; the commit is the authoritative guard since a
            # ticket can be created between the two statements.
            count_res = await session.execute(select(func.count(Ticket.id)).where(Ticket.ticket_type_id == type_id))
            used_count = count_res.scalar_one()
            if used_count > 0:
                raise ValidationException(f"Cannot delete ticket type: {used_count} ticket(s) are currently associated with it.")

            await session.delete(tt)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValidationException(
                    "Cannot delete ticket type: tickets were associated with it while it was being removed."
                ) from None
