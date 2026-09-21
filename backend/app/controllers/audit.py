from typing import Annotated, Optional

from litestar import Controller, get, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.params import QueryParameter
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from app.controllers.auth import get_current_user_from_request
from app.db.session import async_session_factory
from app.models.audit_log import AuditLog
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page


class AuditLogItem(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_name: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    meta_json: Optional[str] = None
    created_at: str


class AuditLogController(Controller):
    path = "/api/audit-logs"

    @get("/")
    async def list_logs(
        self,
        request: Request,
        actor_id: Annotated[Optional[int], QueryParameter()] = None,
        action: Annotated[Optional[str], QueryParameter()] = None,
        entity_type: Annotated[Optional[str], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[AuditLogItem]:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")
        if user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")

        async with async_session_factory() as session:
            filters = []
            if actor_id is not None:
                filters.append(AuditLog.actor_id == actor_id)
            if action:
                filters.append(AuditLog.action == action)
            if entity_type:
                filters.append(AuditLog.entity_type == entity_type)
            total = (
                await session.execute(select(func.count()).select_from(AuditLog).where(*filters))
            ).scalar_one()
            rows = (
                (
                    await session.execute(
                        select(AuditLog)
                        .where(*filters)
                        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            items = [
                AuditLogItem(
                    id=row.id,
                    actor_id=row.actor_id,
                    actor_name=row.actor_name,
                    action=row.action,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    before_json=row.before_json,
                    after_json=row.after_json,
                    meta_json=row.meta_json,
                    created_at=row.created_at.isoformat(),
                )
                for row in rows
            ]
            return Page[AuditLogItem](items=items, total=total, limit=limit, offset=offset)
