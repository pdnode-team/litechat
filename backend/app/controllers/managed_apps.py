from typing import Annotated, Optional
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException, ValidationException
from litestar.params import PathParameter, QueryParameter
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.session import async_session_factory
from app.models.managed_app import ManagedApp
from app.models.ticket import Ticket
from app.schemas.managed_app import ManagedAppCreate, ManagedAppUpdate, ManagedAppResponse
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request
from app.services import events as event_bus

def app_to_response(app: ManagedApp) -> ManagedAppResponse:
    return ManagedAppResponse(
        id=app.id,
        name=app.name,
        code=app.code,
        base_url=app.base_url,
        is_active=app.is_active,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )

class ManagedAppController(Controller):
    path = "/api/apps"

    @get("/")
    async def list_apps(
        self,
        request: Request,
        active_only: Annotated[Optional[bool], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[ManagedAppResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            filters = []
            if active_only:
                filters.append(ManagedApp.is_active.is_(True))

            total = (
                await session.execute(select(func.count()).select_from(ManagedApp).where(*filters))
            ).scalar_one()

            stmt = (
                select(ManagedApp)
                .where(*filters)
                .order_by(ManagedApp.id.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            items = [app_to_response(a) for a in result.scalars().all()]
            return Page[ManagedAppResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/")
    async def create_app(self, request: Request, data: ManagedAppCreate) -> ManagedAppResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage applications.")

        async with async_session_factory() as session:
            # Check unique code
            existing = await session.execute(select(ManagedApp).where(ManagedApp.code == data.code.strip()))
            if existing.scalar_one_or_none():
                raise ValidationException(f"Application with code '{data.code}' already exists.")

            new_app = ManagedApp(
                name=data.name.strip(),
                code=data.code.strip().lower(),
                base_url=data.base_url.strip() if data.base_url else None,
                is_active=data.is_active,
            )
            session.add(new_app)
            await session.commit()
            await session.refresh(new_app)
            await event_bus.publish_catalog_change("apps", "created", actor_name=current_user.full_name)
            return app_to_response(new_app)

    @put("/{app_id:int}")
    async def update_app(self, request: Request, app_id: Annotated[int, PathParameter()], data: ManagedAppUpdate) -> ManagedAppResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage applications.")

        async with async_session_factory() as session:
            app = await session.get(ManagedApp, app_id)
            if not app:
                raise NotFoundException("Application not found.")

            if data.name is not None:
                app.name = data.name.strip()
            if data.code is not None:
                app.code = data.code.strip().lower()
            if data.base_url is not None:
                app.base_url = data.base_url.strip() if data.base_url.strip() else None
            if data.is_active is not None:
                app.is_active = data.is_active

            await session.commit()
            await session.refresh(app)
            await event_bus.publish_catalog_change("apps", "updated", actor_name=current_user.full_name)
            return app_to_response(app)

    @delete("/{app_id:int}")
    async def delete_app(self, request: Request, app_id: Annotated[int, PathParameter()]) -> None:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage applications.")

        async with async_session_factory() as session:
            app = await session.get(ManagedApp, app_id)
            if not app:
                raise NotFoundException("Application not found.")

            # Pre-check for a friendly message; the commit below is the real
            # guard because a ticket can be created between the two statements.
            count_res = await session.execute(select(func.count(Ticket.id)).where(Ticket.app_id == app_id))
            used_count = count_res.scalar_one()
            if used_count > 0:
                raise ValidationException(f"Cannot delete application: {used_count} ticket(s) are currently associated with it.")

            await session.delete(app)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValidationException(
                    "Cannot delete application: tickets were associated with it while it was being removed."
                ) from None

            await event_bus.publish_catalog_change("apps", "deleted", actor_name=current_user.full_name)
