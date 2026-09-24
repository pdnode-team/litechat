import json
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Annotated, List, Optional

from litestar import Controller, get, post, Request
from litestar.datastructures import UploadFile
from litestar.exceptions import (
    NotAuthorizedException,
    NotFoundException,
    ValidationException,
)
from litestar.params import MultipartBody, PathParameter, QueryParameter
from litestar.response import File
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.config import UPLOAD_DIR
from app.controllers.auth import get_current_user_from_request
from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.file_upload import FileUpload
from app.models.message import Message
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.message import AttachmentItem, MessageCreate, MessageResponse
from app.schemas.pagination import (
    DEFAULT_MESSAGE_PAGE_SIZE,
    MessageLimitParam,
    OffsetParam,
    Page,
)
from app.services.access import require_ticket_view
from app.services.form_logic import MAX_DESCRIPTION_LENGTH
from app.services.sla_service import calculate_sla_deadlines
from app.services import events as event_bus
from app.services import notification_service
from app.services.events import Event, MESSAGE_CREATED

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".txt", ".csv", ".log", ".zip", ".doc", ".docx", ".json",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
STORED_FILE_RE = re.compile(r"^/api/files/([A-Za-z0-9._-]+)$")
SAFE_STORED_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def message_to_response(msg: Message, sender_name_override: Optional[str] = None) -> MessageResponse:
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
        sender_name=sender_name_override or msg.sender_name,
        sender_role=msg.sender_role,
        message_type=msg.message_type,
        content=msg.content,
        attachments=attachments,
        created_at=msg.created_at,
    )


def _file_type_for(ext: str) -> str:
    return "image" if ext in IMAGE_EXTENSIONS else "document"


async def _user_can_read_file(session, user: User, stored_name: str) -> bool:
    if user.role in ("agent", "admin"):
        return True
    upload = (
        await session.execute(select(FileUpload).where(FileUpload.stored_name == stored_name))
    ).scalar_one_or_none()
    if upload and upload.uploader_id == user.id:
        return True
    msg = (
        await session.execute(
            select(Message)
            .join(Ticket, Ticket.id == Message.ticket_id)
            .where(
                Message.attachments_json.contains(stored_name),
                Ticket.customer_id == user.id,
                Message.message_type != "whisper",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return msg is not None


async def _resolve_attachments(
    session, user: User, items: Optional[List[AttachmentItem]]
) -> Optional[str]:
    if not items:
        return None
    cleaned: List[dict] = []
    for item in items:
        match = STORED_FILE_RE.match((item.url or "").strip())
        if not match:
            raise ValidationException("Attachments must be files uploaded through this service.")
        stored_name = match.group(1)
        dest = (UPLOAD_DIR / stored_name).resolve()
        if not dest.is_relative_to(UPLOAD_DIR.resolve()) or not dest.is_file():
            raise ValidationException("Unknown attachment.")
        upload = (
            await session.execute(select(FileUpload).where(FileUpload.stored_name == stored_name))
        ).scalar_one_or_none()
        if upload is not None and upload.uploader_id != user.id and user.role not in ("agent", "admin"):
            raise ValidationException("Unknown attachment.")
        ext = Path(stored_name).suffix.lower()
        original = upload.original_name if upload else Path(item.name or stored_name).name
        size = upload.size if upload else dest.stat().st_size
        cleaned.append(
            {
                "name": original[:255],
                "url": f"/api/files/{stored_name}",
                "file_type": _file_type_for(ext),
                "size": size,
            }
        )
    return json.dumps(cleaned)


class MessageController(Controller):
    path = "/api/tickets/{ticket_id:int}/messages"

    @get("/")
    async def list_messages(
        self,
        request: Request,
        ticket_id: Annotated[int, PathParameter()],
        limit: MessageLimitParam = DEFAULT_MESSAGE_PAGE_SIZE,
        offset: OffsetParam = 0,
        before_id: Annotated[Optional[int], QueryParameter()] = None,
    ) -> Page[MessageResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            require_ticket_view(current_user, ticket)

            filters = [Message.ticket_id == ticket_id]
            if current_user.role == "customer":
                filters.append(Message.message_type != "whisper")

            total = (
                await session.execute(select(func.count()).select_from(Message).where(*filters))
            ).scalar_one()

            page_filters = list(filters)
            if before_id is not None:
                pivot = await session.get(Message, before_id)
                if pivot is None or pivot.ticket_id != ticket_id:
                    raise ValidationException("Invalid message cursor.")
                page_filters.append(
                    or_(
                        Message.created_at < pivot.created_at,
                        and_(Message.created_at == pivot.created_at, Message.id < pivot.id),
                    )
                )
                offset = 0

            stmt = (
                select(Message)
                .where(*page_filters)
                .order_by(desc(Message.created_at), desc(Message.id))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            messages = list(reversed(result.scalars().all()))

            sender_ids = {m.sender_id for m in messages if m.sender_id}
            user_names = {}
            if sender_ids:
                users_res = await session.execute(
                    select(User.id, User.full_name).where(User.id.in_(list(sender_ids)))
                )
                user_names = dict(users_res.all())

            items = [
                message_to_response(m, sender_name_override=user_names.get(m.sender_id))
                for m in messages
            ]
            return Page[MessageResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/")
    async def create_message(
        self, request: Request, ticket_id: Annotated[int, PathParameter()], data: MessageCreate
    ) -> MessageResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        content = data.content.strip()
        if not content and not data.attachments:
            raise ValidationException("Message cannot be empty.")
        if len(content) > MAX_DESCRIPTION_LENGTH:
            raise ValidationException(f"Message must be at most {MAX_DESCRIPTION_LENGTH} characters.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            require_ticket_view(current_user, ticket)

            if ticket.status == "closed":
                raise ValidationException("This ticket is closed. Reopen it before sending a message.")

            if current_user.role == "customer":
                safe_message_type = "text"
            elif current_user.role in ("agent", "admin"):
                safe_message_type = data.message_type if data.message_type in ("text", "whisper") else "text"
            else:
                safe_message_type = "text"

            now = utcnow()
            if (
                current_user.role in ("agent", "admin")
                and not ticket.first_responded_at
                and safe_message_type != "whisper"
            ):
                ticket.first_responded_at = now
                if ticket.status == "open":
                    ticket.status = "in_progress"

            if ticket.status == "resolved" and safe_message_type != "whisper":
                ticket.status = "open"
                ticket.resolved_at = None
                ticket.closed_at = None
                _, res_due = await calculate_sla_deadlines(ticket.priority, now)
                ticket.resolution_due_at = res_due

            attachments_json = await _resolve_attachments(session, current_user, data.attachments)

            msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role=current_user.role,
                message_type=safe_message_type,
                content=content,
                attachments_json=attachments_json,
                created_at=now,
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)

            resp = message_to_response(msg)

            is_whisper = safe_message_type == "whisper"
            from_staff = current_user.role in ("agent", "admin")

            if is_whisper:
                email_kind = None
                recipients = set()
                if ticket.assigned_agent_id and ticket.assigned_agent_id != current_user.id:
                    recipients.add(ticket.assigned_agent_id)
            elif from_staff:
                email_kind = notification_service.KIND_STAFF_REPLY
                recipients = {ticket.customer_id}
                if ticket.assigned_agent_id and ticket.assigned_agent_id != current_user.id:
                    recipients.add(ticket.assigned_agent_id)
            else:
                email_kind = notification_service.KIND_CUSTOMER_REPLY
                recipients = {ticket.customer_id}
                if ticket.assigned_agent_id:
                    recipients.add(ticket.assigned_agent_id)

            await event_bus.publish(
                Event(
                    type=MESSAGE_CREATED,
                    notification={
                        "ticket_id": ticket.id,
                        "ticket_code": ticket.ticket_code,
                        "message_id": msg.id,
                        "sender_id": current_user.id,
                        "sender_role": current_user.role,
                        "message_type": safe_message_type,
                        "preview": content[:140],
                        "assigned_agent_id": ticket.assigned_agent_id,
                    },
                    ticket_payload={
                        "type": "new_message",
                        "message": json.loads(resp.model_dump_json()),
                    },
                    ticket_id=ticket.id,
                    user_ids=sorted(recipients),
                    staff=True,
                    whisper=is_whisper,
                    email_kind=email_kind,
                    context={
                        "ticket_id": ticket.id,
                        "ticket_code": ticket.ticket_code,
                        "title": ticket.title,
                        "customer_id": ticket.customer_id,
                        "assigned_agent_id": ticket.assigned_agent_id,
                        "actor_name": current_user.full_name,
                        "actor_email": current_user.email,
                        "message_excerpt": content,
                    },
                )
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
            raise ValidationException(f"File size exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit.")

        raw_name = Path(data.filename or "file").name
        file_ext = Path(raw_name).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValidationException(
                f"File type '{file_ext}' is not permitted. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )

        safe_stem = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(raw_name).stem)[:80]
        if not safe_stem:
            safe_stem = "file"

        unique_name = f"{uuid.uuid4().hex[:12]}_{safe_stem}{file_ext}"
        dest_path = (UPLOAD_DIR / unique_name).resolve()

        if not dest_path.is_relative_to(UPLOAD_DIR.resolve()):
            raise ValidationException("Invalid file destination path detected.")

        with open(dest_path, "wb") as f:
            f.write(file_bytes)

        guessed, _ = mimetypes.guess_type(unique_name)
        content_type = guessed or "application/octet-stream"

        async with async_session_factory() as session:
            session.add(
                FileUpload(
                    stored_name=unique_name,
                    original_name=raw_name[:255],
                    content_type=content_type,
                    size=len(file_bytes),
                    uploader_id=current_user.id,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                dest_path.unlink(missing_ok=True)
                raise ValidationException("Could not store the uploaded file.") from None

        return AttachmentItem(
            name=raw_name,
            url=f"/api/files/{unique_name}",
            file_type=_file_type_for(file_ext),
            size=len(file_bytes),
        )


class FileController(Controller):
    path = "/api/files"

    @get("/{file_name:str}")
    async def get_file(self, request: Request, file_name: Annotated[str, PathParameter()]) -> File:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        stored_name = Path(file_name).name
        if not SAFE_STORED_NAME.match(stored_name):
            raise NotFoundException("File not found.")

        dest = (UPLOAD_DIR / stored_name).resolve()
        if not dest.is_relative_to(UPLOAD_DIR.resolve()) or not dest.is_file():
            raise NotFoundException("File not found.")

        async with async_session_factory() as session:
            if not await _user_can_read_file(session, current_user, stored_name):
                raise NotFoundException("File not found.")
            upload = (
                await session.execute(select(FileUpload).where(FileUpload.stored_name == stored_name))
            ).scalar_one_or_none()

        ext = Path(stored_name).suffix.lower()
        download_name = (upload.original_name if upload else stored_name) or stored_name
        media_type, _ = mimetypes.guess_type(stored_name)
        if ext not in IMAGE_EXTENSIONS:
            media_type = media_type or "application/octet-stream"
        disposition = "inline" if ext in IMAGE_EXTENSIONS else "attachment"

        from app.services import audit as audit_service

        ticket_id = None
        async with async_session_factory() as session:
            msg = (
                await session.execute(
                    select(Message.id, Message.ticket_id).where(Message.attachments_json.contains(stored_name)).limit(1)
                )
            ).first()
            if msg is not None:
                ticket_id = msg.ticket_id
        await audit_service.record(
            actor=current_user,
            action="file.downloaded",
            entity_type="file",
            entity_id=stored_name,
            meta={"ticket_id": ticket_id},
        )

        return File(
            path=dest,
            filename=download_name,
            content_disposition_type=disposition,
            media_type=media_type or "application/octet-stream",
            headers={"x-content-type-options": "nosniff"},
        )
