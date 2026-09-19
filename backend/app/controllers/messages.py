import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, List
from litestar import Controller, get, post, Request
from litestar.datastructures import UploadFile
from litestar.params import MultipartBody, PathParameter
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from sqlalchemy import select, func, desc
from app.config import UPLOAD_DIR
from app.db.session import async_session_factory
from app.models.message import Message
from app.models.ticket import Ticket
from app.schemas.message import MessageCreate, MessageResponse, AttachmentItem
from app.schemas.pagination import (
    DEFAULT_MESSAGE_PAGE_SIZE,
    MessageLimitParam,
    OffsetParam,
    Page,
)
from app.controllers.auth import get_current_user_from_request
from app.services.websocket_hub import hub

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".pdf", ".txt", ".csv", ".log", ".zip", ".doc", ".docx", ".json"
}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB

def message_to_response(msg: Message) -> MessageResponse:
    attachments = None
    if msg.attachments_json:
        try:
            raw_list = json.loads(msg.attachments_json)
            attachments = [AttachmentItem(**item) for item in raw_list]
        except Exception:
            attachments = None

    return MessageResponse(
        id=msg.id,
        ticket_id=msg.ticket_id,
        sender_id=msg.sender_id,
        sender_name=msg.sender_name,
        sender_role=msg.sender_role,
        message_type=msg.message_type,
        content=msg.content,
        attachments=attachments,
        created_at=msg.created_at,
    )

class MessageController(Controller):
    path = "/api/tickets/{ticket_id:int}/messages"

    @get("/")
    async def list_messages(
        self,
        request: Request,
        ticket_id: Annotated[int, PathParameter()],
        limit: MessageLimitParam = DEFAULT_MESSAGE_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[MessageResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            # Strict RBAC: Customer can ONLY access their own ticket messages
            if current_user.role == "customer" and ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You do not have permission to view messages for this ticket.")

            # Whispers are staff-only, so they must be excluded from the count too.
            filters = [Message.ticket_id == ticket_id]
            if current_user.role == "customer":
                filters.append(Message.message_type != "whisper")

            total = (
                await session.execute(select(func.count()).select_from(Message).where(*filters))
            ).scalar_one()

            # Page 0 is the newest slice of the conversation (a chat wants the
            # latest messages first); each page is still returned in
            # chronological order so it can be prepended as-is.
            stmt = (
                select(Message)
                .where(*filters)
                .order_by(desc(Message.created_at), desc(Message.id))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            messages = list(reversed(result.scalars().all()))

            items = [message_to_response(m) for m in messages]
            return Page[MessageResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/")
    async def create_message(self, request: Request, ticket_id: Annotated[int, PathParameter()], data: MessageCreate) -> MessageResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            # Strict RBAC: Customer can only reply to their own ticket
            if current_user.role == "customer":
                if ticket.customer_id != current_user.id:
                    raise PermissionDeniedException("Forbidden: You cannot post messages to this ticket.")

            # Strict message_type enforcement: Customers can ONLY send text messages
            if current_user.role == "customer":
                safe_message_type = "text"
            elif current_user.role in ("agent", "admin"):
                safe_message_type = data.message_type if data.message_type in ("text", "whisper") else "text"
            else:
                safe_message_type = "text"

            now = datetime.now(timezone.utc)
            # If agent first response
            if current_user.role in ("agent", "admin") and not ticket.first_responded_at and safe_message_type != "whisper":
                ticket.first_responded_at = now
                if ticket.status == "open":
                    ticket.status = "in_progress"

            attachments_json = None
            if data.attachments:
                attachments_json = json.dumps([a.model_dump() for a in data.attachments])

            msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role=current_user.role,
                message_type=safe_message_type,
                content=data.content.strip(),
                attachments_json=attachments_json,
                created_at=now,
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)

            resp = message_to_response(msg)

            # Broadcast via WebSocket
            await hub.broadcast(
                ticket.id,
                {
                    "type": "new_message",
                    "message": json.loads(resp.model_dump_json()),
                },
            )

            return resp

class UploadController(Controller):
    path = "/api/upload"

    @post("/")
    async def upload_file(
        self,
        request: Request,
        data: MultipartBody[UploadFile],
    ) -> AttachmentItem:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        file_bytes = await data.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValidationException(f"File size exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit.")

        # Sanitize filename to prevent directory traversal
        raw_name = Path(data.filename or "file").name
        file_ext = Path(raw_name).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValidationException(f"File type '{file_ext}' is not permitted. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

        safe_stem = re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(raw_name).stem)[:80]
        if not safe_stem:
            safe_stem = "file"

        unique_name = f"{uuid.uuid4().hex[:12]}_{safe_stem}{file_ext}"
        dest_path = (UPLOAD_DIR / unique_name).resolve()

        # Enforce path containment within UPLOAD_DIR
        if not dest_path.is_relative_to(UPLOAD_DIR.resolve()):
            raise ValidationException("Invalid file destination path detected.")

        with open(dest_path, "wb") as f:
            f.write(file_bytes)

        url = f"/api/files/{unique_name}"
        file_type = "image" if file_ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"] else "document"

        return AttachmentItem(
            name=raw_name,
            url=url,
            file_type=file_type,
            size=len(file_bytes),
        )
