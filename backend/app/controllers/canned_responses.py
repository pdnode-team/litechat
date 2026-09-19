from typing import List
from litestar import Controller, get, post, patch, delete, Request
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.canned_response import CannedResponse
from app.schemas.canned_response import (
    CannedResponseCreate,
    CannedResponseUpdate,
    CannedResponseResponse,
)
from app.controllers.auth import get_current_user_from_request

class CannedResponseController(Controller):
    path = "/api/canned-responses"

    @get("/")
    async def list_canned(self, request: Request) -> List[CannedResponseResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can access canned responses.")

        async with async_session_factory() as session:
            stmt = select(CannedResponse).order_by(CannedResponse.shortcut.asc())
            res = await session.execute(stmt)
            items = res.scalars().all()
            return [CannedResponseResponse.model_validate(i) for i in items]

    @post("/")
    async def create_canned(self, request: Request, data: CannedResponseCreate) -> CannedResponseResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can manage canned responses.")

        shortcut = data.shortcut if data.shortcut.startswith("/") else f"/{data.shortcut}"

        async with async_session_factory() as session:
            stmt = select(CannedResponse).where(CannedResponse.shortcut == shortcut)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                raise ValidationException(f"Shortcut '{shortcut}' already exists.")

            item = CannedResponse(
                shortcut=shortcut,
                title=data.title.strip(),
                content=data.content.strip(),
                category=data.category,
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return CannedResponseResponse.model_validate(item)

    @patch("/{response_id:int}")
    async def update_canned(self, request: Request, response_id: int, data: CannedResponseUpdate) -> CannedResponseResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can manage canned responses.")

        async with async_session_factory() as session:
            item = await session.get(CannedResponse, response_id)
            if not item:
                raise NotFoundException("Canned response not found.")

            if data.shortcut:
                item.shortcut = data.shortcut if data.shortcut.startswith("/") else f"/{data.shortcut}"
            if data.title:
                item.title = data.title.strip()
            if data.content:
                item.content = data.content.strip()
            if data.category:
                item.category = data.category

            await session.commit()
            await session.refresh(item)
            return CannedResponseResponse.model_validate(item)

    @delete("/{response_id:int}")
    async def delete_canned(self, request: Request, response_id: int) -> None:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can manage canned responses.")

        async with async_session_factory() as session:
            item = await session.get(CannedResponse, response_id)
            if not item:
                raise NotFoundException("Canned response not found.")
            await session.delete(item)
            await session.commit()
