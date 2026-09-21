from typing import Annotated
from litestar import Controller, get, post, patch, delete, Request
from litestar.params import PathParameter
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
)
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.errors import is_unique_violation
from app.db.session import async_session_factory
from app.exceptions import FormValidationError
from app.models.canned_response import CannedResponse
from app.schemas.canned_response import (
    MAX_SHORTCUT_LENGTH,
    CannedResponseCreate,
    CannedResponseUpdate,
    CannedResponseResponse,
)
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request
from app.services import events as event_bus
from app.services.form_logic import FieldError


def normalise_shortcut(raw: str) -> str:
    """Shortcuts are stored with a leading slash so they can be typed inline."""
    value = raw.strip()
    return value if value.startswith("/") else f"/{value}"


def shortcut_problems(shortcut: str) -> list:
    """The stored value carries the slash, so the limit applies *after* prefixing."""
    if len(shortcut) > MAX_SHORTCUT_LENGTH:
        return [
            FieldError(
                "shortcut",
                f"The shortcut must be at most {MAX_SHORTCUT_LENGTH} characters "
                "(including the leading '/').",
                "Shortcut",
                "too_long",
            )
        ]
    return []


def duplicate_shortcut_error(shortcut: str) -> FormValidationError:
    return FormValidationError(
        [FieldError("shortcut", f"The shortcut '{shortcut}' already exists.", "Shortcut", "duplicate")]
    )


class CannedResponseController(Controller):
    path = "/api/canned-responses"

    @get("/")
    async def list_canned(
        self,
        request: Request,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[CannedResponseResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can access canned responses.")

        async with async_session_factory() as session:
            total = (
                await session.execute(select(func.count()).select_from(CannedResponse))
            ).scalar_one()
            stmt = (
                select(CannedResponse)
                .order_by(CannedResponse.shortcut.asc())
                .limit(limit)
                .offset(offset)
            )
            res = await session.execute(stmt)
            items = [CannedResponseResponse.model_validate(i) for i in res.scalars().all()]
            return Page[CannedResponseResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/")
    async def create_canned(self, request: Request, data: CannedResponseCreate) -> CannedResponseResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can manage canned responses.")

        shortcut = normalise_shortcut(data.shortcut)
        problems = shortcut_problems(shortcut)
        if problems:
            raise FormValidationError(problems)

        async with async_session_factory() as session:
            stmt = select(CannedResponse).where(CannedResponse.shortcut == shortcut)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                raise duplicate_shortcut_error(shortcut)

            title = data.title.strip()
            content = data.content.strip()
            if not title:
                raise FormValidationError([FieldError("title", "A title is required.", "Title", "required")])
            if not content:
                raise FormValidationError([FieldError("content", "Content is required.", "Content", "required")])

            item = CannedResponse(
                shortcut=shortcut,
                title=title,
                content=content,
                category=data.category,
            )
            session.add(item)
            try:
                await session.commit()
            except IntegrityError as exc:
                # Another user may have taken the shortcut since the check above.
                await session.rollback()
                if not is_unique_violation(exc, ("ix_canned_responses_shortcut", "canned_responses.shortcut")):
                    raise
                raise duplicate_shortcut_error(shortcut) from None
            await session.refresh(item)
            await event_bus.publish_catalog_change(
                "canned_responses", "created", actor_name=current_user.full_name
            )
            return CannedResponseResponse.model_validate(item)

    @patch("/{response_id:int}")
    async def update_canned(self, request: Request, response_id: Annotated[int, PathParameter()], data: CannedResponseUpdate) -> CannedResponseResponse:
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
                shortcut = normalise_shortcut(data.shortcut)
                problems = shortcut_problems(shortcut)
                if problems:
                    raise FormValidationError(problems)
                if shortcut != item.shortcut:
                    clash = await session.execute(
                        select(CannedResponse).where(
                            CannedResponse.shortcut == shortcut, CannedResponse.id != item.id
                        )
                    )
                    if clash.scalar_one_or_none():
                        raise duplicate_shortcut_error(shortcut)
                item.shortcut = shortcut
            if data.title:
                item.title = data.title.strip()
            if data.content:
                item.content = data.content.strip()
            if data.category:
                item.category = data.category

            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if not is_unique_violation(exc, ("ix_canned_responses_shortcut", "canned_responses.shortcut")):
                    raise
                raise duplicate_shortcut_error(item.shortcut) from None
            await session.refresh(item)
            await event_bus.publish_catalog_change(
                "canned_responses", "updated", actor_name=current_user.full_name
            )
            return CannedResponseResponse.model_validate(item)

    @delete("/{response_id:int}")
    async def delete_canned(self, request: Request, response_id: Annotated[int, PathParameter()]) -> None:
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

        await event_bus.publish_catalog_change(
            "canned_responses", "deleted", actor_name=current_user.full_name
        )
        from app.services import audit as audit_service
        await audit_service.record(
            actor=current_user, action="canned_response.deleted", entity_type="canned_response", entity_id=response_id
        )
