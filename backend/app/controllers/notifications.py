from typing import List, Optional

from litestar import Controller, get, post, Request
from litestar.exceptions import NotAuthorizedException
from pydantic import BaseModel
from sqlalchemy import case, desc, func, select, update

from app.controllers.auth import get_current_user_from_request
from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.notification import Notification
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page


class NotificationItem(BaseModel):
    id: int
    type: str
    title: str
    body: str
    ticket_id: Optional[int] = None
    read_at: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class MarkReadRequest(BaseModel):
    ids: Optional[List[int]] = None
    all: bool = False


def _item(row: Notification) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        type=row.type,
        title=row.title,
        body=row.body,
        ticket_id=row.ticket_id,
        read_at=row.read_at.isoformat() if row.read_at else None,
        created_at=row.created_at.isoformat(),
    )


class NotificationController(Controller):
    path = "/api/notifications"

    @get("/")
    async def list_notifications(
        self,
        request: Request,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[NotificationItem]:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            filters = [Notification.user_id == user.id]
            total = (
                await session.execute(select(func.count()).select_from(Notification).where(*filters))
            ).scalar_one()
            unread_first = case((Notification.read_at.is_(None), 0), else_=1)
            rows = (
                (
                    await session.execute(
                        select(Notification)
                        .where(*filters)
                        .order_by(unread_first, desc(Notification.created_at), desc(Notification.id))
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            return Page[NotificationItem](
                items=[_item(row) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
            )

    @post("/read")
    async def mark_read(self, request: Request, data: MarkReadRequest) -> dict:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")

        now = utcnow()
        async with async_session_factory() as session:
            stmt = (
                update(Notification)
                .where(Notification.user_id == user.id, Notification.read_at.is_(None))
                .values(read_at=now)
            )
            if not data.all:
                ids = data.ids or []
                if not ids:
                    return {"updated": 0}
                stmt = stmt.where(Notification.id.in_(ids))
            result = await session.execute(stmt)
            await session.commit()
            return {"updated": result.rowcount or 0}
