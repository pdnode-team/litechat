from typing import List, Optional
from litestar import Controller, get, patch, Request
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from pydantic import BaseModel
from sqlalchemy import select, desc
from app.db.session import async_session_factory
from app.models.user import User
from app.schemas.auth import UserResponse
from app.controllers.auth import get_current_user_from_request

class UpdateRoleRequest(BaseModel):
    role: str  # customer, agent, admin

class UpdateStatusRequest(BaseModel):
    is_active: bool

class UserController(Controller):
    path = "/api/users"

    @get("/")
    async def list_users(self, request: Request, role: Optional[str] = None) -> List[UserResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")

        async with async_session_factory() as session:
            stmt = select(User).order_by(desc(User.created_at))
            if role:
                stmt = stmt.where(User.role == role)
            res = await session.execute(stmt)
            users = res.scalars().all()
            return [UserResponse.model_validate(u) for u in users]

    @patch("/{user_id:int}/role")
    async def update_user_role(self, request: Request, user_id: int, data: UpdateRoleRequest) -> UserResponse:
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
            return UserResponse.model_validate(user)

    @patch("/{user_id:int}/status")
    async def update_user_status(self, request: Request, user_id: int, data: UpdateStatusRequest) -> UserResponse:
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
            await session.commit()
            await session.refresh(user)
            return UserResponse.model_validate(user)
