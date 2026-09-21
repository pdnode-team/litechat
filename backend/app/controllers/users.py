from typing import Annotated, List, Optional
from urllib.parse import urlparse

from litestar import Controller, get, patch, Request
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from litestar.params import PathParameter, QueryParameter
from pydantic import BaseModel
from sqlalchemy import select, desc, func, or_
from app.db.search import LIKE_ESCAPE, like_contains
from app.services.websocket_hub import hub
from app.db.session import async_session_factory
from app.exceptions import FormValidationError
from app.models.user import User
from app.schemas.auth import ProfileUpdateRequest, UserResponse
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request
from app.services import events as event_bus
from app.services.form_logic import FieldError

class UpdateRoleRequest(BaseModel):
    role: str  # customer, agent, admin

class UpdateStatusRequest(BaseModel):
    is_active: bool

class UserController(Controller):
    path = "/api/users"

    @get("/")
    async def list_users(
        self,
        request: Request,
        role: Annotated[Optional[str], QueryParameter()] = None,
        search: Annotated[Optional[str], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[UserResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")

        async with async_session_factory() as session:
            filters = []
            if role:
                filters.append(User.role == role)
            if search:
                term = like_contains(search.strip())
                filters.append(
                    or_(
                        User.email.ilike(term, escape=LIKE_ESCAPE),
                        User.username.ilike(term, escape=LIKE_ESCAPE),
                        User.full_name.ilike(term, escape=LIKE_ESCAPE),
                    )
                )

            total = (
                await session.execute(select(func.count()).select_from(User).where(*filters))
            ).scalar_one()

            stmt = (
                select(User)
                .where(*filters)
                .order_by(desc(User.created_at), desc(User.id))
                .limit(limit)
                .offset(offset)
            )
            users = (await session.execute(stmt)).scalars().all()
            items = [UserResponse.model_validate(u) for u in users]
            return Page[UserResponse](items=items, total=total, limit=limit, offset=offset)

    @get("/assignable")
    async def list_assignable_staff(self, request: Request) -> List[UserResponse]:
        """Active staff an agent can hand a ticket to.

        Kept separate from the administrator-only user list so agents can use the
        reassignment picker without seeing customer accounts.
        """
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can view assignable staff.")

        async with async_session_factory() as session:
            stmt = (
                select(User)
                .where(User.role.in_(["agent", "admin"]), User.is_active.is_(True))
                .order_by(User.full_name.asc())
            )
            users = (await session.execute(stmt)).scalars().all()
            return [UserResponse.model_validate(u) for u in users]

    @patch("/me")
    async def update_me(self, request: Request, data: ProfileUpdateRequest) -> UserResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        errors: list[FieldError] = []
        full_name = data.full_name
        if full_name is not None:
            full_name = full_name.strip()
            if len(full_name) < 2:
                errors.append(
                    FieldError("full_name", "Display name must be at least 2 characters.", "Display name", "too_short")
                )
            elif len(full_name) > 150:
                errors.append(
                    FieldError("full_name", "Display name must be at most 150 characters.", "Display name", "too_long")
                )

        avatar_url = data.avatar_url
        if avatar_url is not None:
            avatar_url = avatar_url.strip()
            if avatar_url == "":
                avatar_url = None
            elif len(avatar_url) > 500:
                errors.append(
                    FieldError("avatar_url", "Avatar URL must be at most 500 characters.", "Avatar URL", "too_long")
                )
            else:
                parsed = urlparse(avatar_url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append(
                        FieldError("avatar_url", "Avatar URL must be an http or https link.", "Avatar URL", "invalid")
                    )

        if errors:
            raise FormValidationError(errors)

        async with async_session_factory() as session:
            user = await session.get(User, current_user.id)
            if not user:
                raise NotAuthorizedException("Authentication required.")
            if full_name is not None:
                user.full_name = full_name
            if data.avatar_url is not None:
                user.avatar_url = avatar_url
            await session.commit()
            await session.refresh(user)
            return UserResponse.model_validate(user)

    @patch("/{user_id:int}/role")
    async def update_user_role(self, request: Request, user_id: Annotated[int, PathParameter()], data: UpdateRoleRequest) -> UserResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")

        valid_roles = ["customer", "agent", "admin"]
        if data.role not in valid_roles:
            raise ValidationException(f"Invalid role: {data.role}. Allowed: {valid_roles}")

        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                raise NotFoundException("User not found.")

            if user.id == current_user.id and data.role != "admin":
                raise ValidationException("Cannot demote your own admin account.")

            user.role = data.role
            await session.commit()
            await session.refresh(user)

            await event_bus.publish_user_change(
                user.id,
                "role_changed",
                actor_name=current_user.full_name,
                actor_user_id=current_user.id,
            )
            return UserResponse.model_validate(user)

    @patch("/{user_id:int}/status")
    async def update_user_status(self, request: Request, user_id: Annotated[int, PathParameter()], data: UpdateStatusRequest) -> UserResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")

        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                raise NotFoundException("User not found.")

            if user.id == current_user.id and not data.is_active:
                raise ValidationException("Cannot deactivate your own account.")

            user.is_active = data.is_active
            if not data.is_active:
                user.token_version = (user.token_version or 0) + 1
            await session.commit()
            await session.refresh(user)
            if not data.is_active:
                await hub.disconnect_user(user.id)

            await event_bus.publish_user_change(
                user.id,
                "status_changed",
                actor_name=current_user.full_name,
                actor_user_id=current_user.id,
            )
            return UserResponse.model_validate(user)
