import re
from typing import Annotated, Any, Dict, List, Optional
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException, ValidationException
from litestar.params import PathParameter, QueryParameter
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.errors import is_unique_violation
from app.db.session import async_session_factory
from app.exceptions import FormValidationError
from app.models.managed_app import ManagedApp
from app.models.ticket import Ticket
from app.schemas.managed_app import ManagedAppCreate, ManagedAppUpdate, ManagedAppResponse
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request
from app.services import events as event_bus
from app.services.form_logic import FieldError

# Column limits from app/models/managed_app.py. A value beyond one of these is a
# StringDataRightTruncation on PostgreSQL (i.e. an opaque 500) while SQLite
# silently stores it, so they are enforced here first.
MAX_NAME_LENGTH = 100
MAX_CODE_LENGTH = 50
MAX_BASE_URL_LENGTH = 255
CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_managed_app_payload(
    *,
    name: Optional[str],
    code: Optional[str],
    base_url: Optional[str],
    require_all: bool,
) -> tuple[Dict[str, Any], List[FieldError]]:
    """Validate and clean a managed application payload.

    ``require_all`` is True for a create (name and code are mandatory) and False
    for a partial update, where only the fields actually provided are checked.
    """
    errors: List[FieldError] = []
    cleaned: Dict[str, Any] = {}

    if require_all or name is not None:
        value = (name or "").strip()
        if not value:
            errors.append(FieldError("name", "An application name is required.", "Name", "required"))
        elif len(value) > MAX_NAME_LENGTH:
            errors.append(
                FieldError(
                    "name",
                    f"The application name must be at most {MAX_NAME_LENGTH} characters.",
                    "Name",
                    "too_long",
                )
            )
        else:
            cleaned["name"] = value

    if require_all or code is not None:
        # The stored code is always lowercase, so it is normalised before it is
        # compared or written; otherwise "MyApp" slips past the duplicate check
        # and dies on the unique index instead.
        value = (code or "").strip().lower()
        if not value:
            errors.append(FieldError("code", "An application code is required.", "Code", "required"))
        elif len(value) > MAX_CODE_LENGTH:
            errors.append(
                FieldError(
                    "code",
                    f"The application code must be at most {MAX_CODE_LENGTH} characters.",
                    "Code",
                    "too_long",
                )
            )
        elif not CODE_PATTERN.match(value):
            errors.append(
                FieldError(
                    "code",
                    "The code may only contain letters, digits, dots, dashes and underscores, "
                    "and must start with a letter or a digit.",
                    "Code",
                    "invalid_format",
                )
            )
        else:
            cleaned["code"] = value

    if require_all or base_url is not None:
        value = (base_url or "").strip()
        if not value:
            # An empty string clears the URL rather than storing one.
            cleaned["base_url"] = None
        elif len(value) > MAX_BASE_URL_LENGTH:
            errors.append(
                FieldError(
                    "base_url",
                    f"The base URL must be at most {MAX_BASE_URL_LENGTH} characters.",
                    "Base URL",
                    "too_long",
                )
            )
        elif not value.startswith(("http://", "https://")):
            errors.append(
                FieldError(
                    "base_url",
                    "The base URL must start with http:// or https://",
                    "Base URL",
                    "invalid_url",
                )
            )
        else:
            cleaned["base_url"] = value

    return cleaned, errors


def duplicate_code_error(code: str) -> FormValidationError:
    return FormValidationError(
        [FieldError("code", f"An application with the code '{code}' already exists.", "Code", "duplicate")]
    )


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
            if current_user.role == "customer" or active_only:
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
            cleaned, problems = validate_managed_app_payload(
                name=data.name, code=data.code, base_url=data.base_url, require_all=True
            )
            if problems:
                raise FormValidationError(problems)

            # Friendly pre-check on the normalised code; the unique index below is
            # the authoritative guard because another admin can insert between the
            # two statements.
            existing = await session.execute(select(ManagedApp).where(ManagedApp.code == cleaned["code"]))
            if existing.scalar_one_or_none():
                raise duplicate_code_error(cleaned["code"])

            new_app = ManagedApp(
                name=cleaned["name"],
                code=cleaned["code"],
                base_url=cleaned["base_url"],
                is_active=data.is_active,
            )
            session.add(new_app)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if not is_unique_violation(exc, ("ix_managed_apps_code", "managed_apps.code")):
                    raise
                raise duplicate_code_error(cleaned["code"]) from None
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

            cleaned, problems = validate_managed_app_payload(
                name=data.name, code=data.code, base_url=data.base_url, require_all=False
            )
            if problems:
                raise FormValidationError(problems)

            if "code" in cleaned and cleaned["code"] != app.code:
                clash = await session.execute(
                    select(ManagedApp).where(ManagedApp.code == cleaned["code"], ManagedApp.id != app.id)
                )
                if clash.scalar_one_or_none():
                    raise duplicate_code_error(cleaned["code"])

            if "name" in cleaned:
                app.name = cleaned["name"]
            if "code" in cleaned:
                app.code = cleaned["code"]
            if "base_url" in cleaned:
                app.base_url = cleaned["base_url"]
            if data.is_active is not None:
                app.is_active = data.is_active

            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if not is_unique_violation(exc, ("ix_managed_apps_code", "managed_apps.code")):
                    raise
                raise duplicate_code_error(cleaned.get("code", app.code)) from None
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
