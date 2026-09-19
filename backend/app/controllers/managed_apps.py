from typing import List, Optional
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException, ValidationException
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.managed_app import ManagedApp
from app.schemas.managed_app import ManagedAppCreate, ManagedAppUpdate, ManagedAppResponse
from app.controllers.auth import get_current_user_from_request

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
    async def list_apps(self, request: Request, active_only: Optional[bool] = None) -> List[ManagedAppResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            stmt = select(ManagedApp).order_by(ManagedApp.id.asc())
            if active_only:
                stmt = stmt.where(ManagedApp.is_active.is_(True))
            result = await session.execute(stmt)
            apps = result.scalars().all()
            return [app_to_response(a) for a in apps]

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
            return app_to_response(new_app)

    @put("/{app_id:int}")
    async def update_app(self, request: Request, app_id: int, data: ManagedAppUpdate) -> ManagedAppResponse:
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
            return app_to_response(app)

    @delete("/{app_id:int}")
    async def delete_app(self, request: Request, app_id: int) -> None:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can manage applications.")

        async with async_session_factory() as session:
            app = await session.get(ManagedApp, app_id)
            if not app:
                raise NotFoundException("Application not found.")

            from app.models.ticket import Ticket
            from sqlalchemy import func
            count_res = await session.execute(select(func.count(Ticket.id)).where(Ticket.app_id == app_id))
            used_count = count_res.scalar_one()
            if used_count > 0:
                raise ValidationException(f"Cannot delete application: {used_count} ticket(s) are currently associated with it.")

            await session.delete(app)
            await session.commit()
