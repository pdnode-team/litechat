import json
import secrets
import uuid
from typing import Annotated, Any, Dict, List, Optional
from litestar import Controller, get, post, patch, Request
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from litestar.params import PathParameter, QueryParameter
from sqlalchemy import select, or_, desc, func
from app.db.session import async_session_factory
from app.db.base import utcnow
from app.models.ticket import Ticket
from app.models.user import User
from app.models.message import Message
from app.models.managed_app import ManagedApp
from app.models.ticket_type import TicketType
from app.exceptions import FormValidationError
from app.schemas.pagination import (
    DEFAULT_PAGE_SIZE,
    LimitParam,
    OffsetParam,
    Page,
)
from app.schemas.ticket import (
    TicketCreate,
    TicketResponse,
    TicketStatusUpdateRequest,
    TicketAssignRequest,
    TicketPriorityUpdateRequest,
    TicketUpdateRequest,
)
from app.schemas.ticket_type import CustomFieldDefinition
from app.schemas.auth import UserResponse
from app.schemas.message import MessageResponse
from app.controllers.auth import get_current_user_from_request
from app.controllers.managed_apps import app_to_response
from app.controllers.messages import message_to_response
from app.controllers.ticket_types import parse_fields_schema, type_to_response
from app.services.form_logic import (
    MAX_CUSTOM_FIELDS_JSON_BYTES,
    FieldError,
    validate_base_fields,
    validate_custom_fields,
)
from app.services.sla_service import calculate_sla_deadlines, get_sla_status
from app.services import events as event_bus
from app.services import notification_service
from app.services.events import Event, TICKET_CREATED, TICKET_UPDATED


async def publish_ticket_event(
    ticket: Ticket,
    resp: TicketResponse,
    *,
    reason: str,
    event_type: str = TICKET_UPDATED,
    email_kind: Optional[str] = None,
    context: Optional[dict] = None,
    actor_name: str = "Someone",
    system_message: Optional[MessageResponse] = None,
) -> None:
    """Fan a ticket change out to the conversation room, the queue and email.

    Ticket events reach the owning customer, the assignee, and every staff
    member, so an agent's queue updates live even for tickets they are not
    looking at.

    ``system_message`` is the action card the mutation just wrote into the
    conversation ("Ticket status changed from ... to ..."). It travels in the
    same ticket payload because the conversation view only appends messages it
    receives: without it the card stayed invisible until a manual reload.
    """
    recipients = {ticket.customer_id}
    if ticket.assigned_agent_id:
        recipients.add(ticket.assigned_agent_id)

    ticket_payload: Dict[str, Any] = {"type": event_type, "ticket": resp.model_dump(mode="json")}
    if system_message is not None:
        ticket_payload["message"] = json.loads(system_message.model_dump_json())

    await event_bus.publish(
        Event(
            type=event_type,
            notification={
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "assigned_agent_id": ticket.assigned_agent_id,
                "customer_id": ticket.customer_id,
                "reason": reason,
                "message_id": system_message.id if system_message else None,
            },
            ticket_payload=ticket_payload,
            ticket_id=ticket.id,
            user_ids=sorted(recipients),
            staff=True,
            email_kind=email_kind,
            context={
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "customer_id": ticket.customer_id,
                "assigned_agent_id": ticket.assigned_agent_id,
                "actor_name": actor_name,
                **(context or {}),
            },
        )
    )


def build_ticket_response(
    ticket: Ticket,
    customer: Optional[User],
    agent: Optional[User],
    app: Optional[ManagedApp] = None,
    ticket_type: Optional[TicketType] = None,
) -> TicketResponse:
    first_resp_sla = get_sla_status(ticket.first_response_due_at, ticket.first_responded_at)
    resolution_sla = get_sla_status(ticket.resolution_due_at, ticket.resolved_at)

    custom_fields = None
    if ticket.custom_fields_json:
        try:
            custom_fields = json.loads(ticket.custom_fields_json)
        except Exception:
            custom_fields = None

    return TicketResponse(
        id=ticket.id,
        ticket_code=ticket.ticket_code,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        category=ticket.category,
        customer_id=ticket.customer_id,
        assigned_agent_id=ticket.assigned_agent_id,
        customer=UserResponse.model_validate(customer) if customer else None,
        assigned_agent=UserResponse.model_validate(agent) if agent else None,
        app_id=ticket.app_id,
        app=app_to_response(app) if app else None,
        target_url=ticket.target_url,
        ticket_type_id=ticket.ticket_type_id,
        ticket_type=type_to_response(ticket_type) if ticket_type else None,
        custom_fields=custom_fields,
        first_response_due_at=ticket.first_response_due_at,
        resolution_due_at=ticket.resolution_due_at,
        first_responded_at=ticket.first_responded_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        sla_first_response_status=first_resp_sla,
        sla_resolution_status=resolution_sla,
        tags=ticket.tags or "",
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )

class TicketController(Controller):
    path = "/api/tickets"

    @post("/")
    async def create_ticket(self, request: Request, data: TicketCreate) -> TicketResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        # Naive UTC: every DateTime column is timezone-naive, and asyncpg refuses
        # to bind an aware datetime to one (it raises on PostgreSQL, silently
        # works on SQLite — so this only ever broke in production).
        now = utcnow()

        async with async_session_factory() as session:
            ticket_code = None
            for _ in range(10):
                candidate = f"TCK-{now.year}-{secrets.token_hex(3).upper()}"
                existing = await session.execute(select(Ticket).where(Ticket.ticket_code == candidate))
                if not existing.scalar_one_or_none():
                    ticket_code = candidate
                    break
            if not ticket_code:
                ticket_code = f"TCK-{now.year}-{uuid.uuid4().hex[:8].upper()}"

            # Resolve the optional relations first. A missing or retired target
            # used to be stored as-is (a dangling reference on SQLite) or to blow
            # up as a foreign-key violation at commit time (Postgres, i.e. a 500).
            # It is a client error, and the client deserves to be told which one.
            problems: List[FieldError] = []

            managed_app = None
            if data.app_id:
                managed_app = await session.get(ManagedApp, data.app_id)
                if not managed_app:
                    problems.append(
                        FieldError("app_id", "The selected application does not exist.", "Application", "not_found")
                    )
                elif not managed_app.is_active:
                    problems.append(
                        FieldError(
                            "app_id",
                            f"The application '{managed_app.name}' is retired and no longer accepts tickets.",
                            "Application",
                            "inactive",
                        )
                    )

            t_type = None
            fields_schema: List[CustomFieldDefinition] = []
            if data.ticket_type_id:
                t_type = await session.get(TicketType, data.ticket_type_id)
                if not t_type:
                    problems.append(
                        FieldError(
                            "ticket_type_id",
                            "The selected ticket type does not exist.",
                            "Ticket type",
                            "not_found",
                        )
                    )
                elif not t_type.is_active:
                    problems.append(
                        FieldError(
                            "ticket_type_id",
                            f"The ticket type '{t_type.name}' is no longer available.",
                            "Ticket type",
                            "inactive",
                        )
                    )
                else:
                    fields_schema = parse_fields_schema(t_type.fields_schema_json)

            # Built-in fields, then the answers to the dynamic form.
            cleaned, base_problems = validate_base_fields(
                title=data.title,
                description=data.description,
                tags=data.tags,
                target_url=data.target_url,
                category=data.category,
                priority=data.priority,
            )
            problems.extend(base_problems)

            if t_type is None:
                custom_fields: Dict[str, Any] = {}
                if data.custom_fields:
                    problems.append(
                        FieldError(
                            "custom_fields",
                            "Custom fields require a valid ticket type.",
                            "Custom fields",
                            "unexpected_fields",
                        )
                    )
            else:
                custom_fields, custom_problems = validate_custom_fields(fields_schema, data.custom_fields)
                problems.extend(custom_problems)

            if problems:
                # Every rejected input at once, addressed by field, so the form
                # can highlight all of them instead of one per attempt.
                raise FormValidationError(problems)

            custom_fields_json = json.dumps(custom_fields) if custom_fields else "{}"
            if len(custom_fields_json.encode("utf-8")) > MAX_CUSTOM_FIELDS_JSON_BYTES:
                raise FormValidationError(
                    [
                        FieldError(
                            "custom_fields",
                            "The submitted answers are too large to store.",
                            "Custom fields",
                            "too_large",
                        )
                    ]
                )

            first_due, res_due = calculate_sla_deadlines(cleaned["priority"], now)

            ticket = Ticket(
                ticket_code=ticket_code,
                title=cleaned["title"],
                description=cleaned["description"],
                status="open",
                priority=cleaned["priority"],
                category=cleaned["category"],
                customer_id=current_user.id,
                app_id=managed_app.id if managed_app else None,
                target_url=cleaned["target_url"],
                ticket_type_id=t_type.id if t_type else None,
                custom_fields_json=custom_fields_json,
                first_response_due_at=first_due,
                resolution_due_at=res_due,
                tags=cleaned["tags"],
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)

            # Record customer initial message
            initial_msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role=current_user.role,
                message_type="text",
                content=cleaned["description"],
            )
            session.add(initial_msg)
            await session.commit()

            resp = build_ticket_response(
                ticket,
                customer=current_user,
                agent=None,
                app=managed_app,
                ticket_type=t_type,
            )

            # New tickets appear instantly in every agent's queue, and staff are
            # emailed so an unclaimed ticket does not sit unnoticed.
            await publish_ticket_event(
                ticket,
                resp,
                reason="created",
                event_type=TICKET_CREATED,
                email_kind=notification_service.KIND_NEW_TICKET,
                actor_name=current_user.full_name,
                context={"actor_email": current_user.email, "message_excerpt": ticket.description},
            )
            return resp

    @get("/")
    async def list_tickets(
        self,
        request: Request,
        status: Annotated[Optional[str], QueryParameter()] = None,
        priority: Annotated[Optional[str], QueryParameter()] = None,
        category: Annotated[Optional[str], QueryParameter()] = None,
        search: Annotated[Optional[str], QueryParameter()] = None,
        assigned_to_me: Annotated[Optional[bool], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[TicketResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            # Build the filter set once so the total and the page always agree.
            filters = []
            # Strictly enforce: Customers see ONLY their own tickets
            if current_user.role == "customer":
                filters.append(Ticket.customer_id == current_user.id)
            elif assigned_to_me and current_user.role in ("agent", "admin"):
                filters.append(Ticket.assigned_agent_id == current_user.id)

            if status:
                filters.append(Ticket.status == status)
            if priority:
                filters.append(Ticket.priority == priority)
            if category:
                filters.append(Ticket.category == category)
            if search:
                term = f"%{search.strip()}%"
                filters.append(
                    or_(
                        Ticket.title.ilike(term),
                        Ticket.ticket_code.ilike(term),
                        Ticket.description.ilike(term),
                    )
                )

            total = (
                await session.execute(select(func.count()).select_from(Ticket).where(*filters))
            ).scalar_one()

            stmt = (
                select(Ticket)
                .where(*filters)
                .order_by(desc(Ticket.created_at), desc(Ticket.id))
                .limit(limit)
                .offset(offset)
            )
            tickets = (await session.execute(stmt)).scalars().all()

            user_ids = set()
            app_ids = set()
            type_ids = set()
            for t in tickets:
                user_ids.add(t.customer_id)
                if t.assigned_agent_id:
                    user_ids.add(t.assigned_agent_id)
                if t.app_id:
                    app_ids.add(t.app_id)
                if t.ticket_type_id:
                    type_ids.add(t.ticket_type_id)

            users_map = {}
            if user_ids:
                users_res = await session.execute(select(User).where(User.id.in_(list(user_ids))))
                for u in users_res.scalars().all():
                    users_map[u.id] = u

            apps_map = {}
            if app_ids:
                apps_res = await session.execute(select(ManagedApp).where(ManagedApp.id.in_(list(app_ids))))
                for a in apps_res.scalars().all():
                    apps_map[a.id] = a

            types_map = {}
            if type_ids:
                types_res = await session.execute(select(TicketType).where(TicketType.id.in_(list(type_ids))))
                for tt in types_res.scalars().all():
                    types_map[tt.id] = tt

            items = [
                build_ticket_response(
                    t,
                    customer=users_map.get(t.customer_id),
                    agent=users_map.get(t.assigned_agent_id) if t.assigned_agent_id else None,
                    app=apps_map.get(t.app_id) if t.app_id else None,
                    ticket_type=types_map.get(t.ticket_type_id) if t.ticket_type_id else None,
                )
                for t in tickets
            ]

            return Page[TicketResponse](items=items, total=total, limit=limit, offset=offset)

    @get("/{ticket_id:int}")
    async def get_ticket(self, request: Request, ticket_id: Annotated[int, PathParameter()]) -> TicketResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            # Strict RBAC: Customers cannot view other users' tickets
            if current_user.role == "customer" and ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You do not have permission to view this ticket.")

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None

            return build_ticket_response(
                ticket,
                customer=customer,
                agent=agent,
                app=app,
                ticket_type=ticket_type,
            )

    @patch("/{ticket_id:int}")
    async def update_ticket(
        self,
        request: Request,
        ticket_id: Annotated[int, PathParameter()],
        data: TicketUpdateRequest,
    ) -> TicketResponse:
        """Edit the ticket's descriptive fields (title, description, category, tags, URL)."""
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            if current_user.role == "customer" and ticket.customer_id != current_user.id:
                raise PermissionDeniedException("Forbidden: You cannot modify this ticket.")

            if ticket.status in ("closed",) and current_user.role == "customer":
                raise ValidationException("This ticket is closed. Reopen it before editing.")

            changes = []
            if data.title is not None and data.title.strip() != ticket.title:
                changes.append(f"title -> '{data.title.strip()}'")
                ticket.title = data.title.strip()
            if data.description is not None and data.description.strip() != ticket.description:
                changes.append("description updated")
                ticket.description = data.description.strip()
            if data.category is not None and data.category != ticket.category:
                changes.append(f"category {ticket.category} -> {data.category}")
                ticket.category = data.category
            if data.tags is not None and data.tags != (ticket.tags or ""):
                changes.append("tags updated")
                ticket.tags = data.tags
            if data.target_url is not None:
                new_url = data.target_url.strip() or None
                if new_url != ticket.target_url:
                    changes.append("target URL updated")
                    ticket.target_url = new_url

            action_msg: Optional[Message] = None
            if changes:
                action_msg = Message(
                    ticket_id=ticket.id,
                    sender_id=current_user.id,
                    sender_name=current_user.full_name,
                    sender_role="system",
                    message_type="action_card",
                    content=f"Ticket details edited by {current_user.full_name}: {', '.join(changes)}",
                )
                session.add(action_msg)
                await session.commit()
                await session.refresh(ticket)
                await session.refresh(action_msg)

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=agent, app=app, ticket_type=ticket_type)

            if changes:
                await publish_ticket_event(
                    ticket,
                    resp,
                    reason="details_edited",
                    actor_name=current_user.full_name,
                    system_message=message_to_response(action_msg) if action_msg else None,
                )
            return resp

    @patch("/{ticket_id:int}/status")
    async def update_status(self, request: Request, ticket_id: Annotated[int, PathParameter()], data: TicketStatusUpdateRequest) -> TicketResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        valid_statuses = ["open", "pending", "in_progress", "resolved", "closed"]
        if data.status not in valid_statuses:
            raise ValidationException(f"Invalid status: {data.status}")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            # Strict RBAC: Customer can only update status on their own ticket
            if current_user.role == "customer":
                if ticket.customer_id != current_user.id:
                    raise PermissionDeniedException("Forbidden: You cannot modify this ticket.")
                if data.status not in ["resolved", "closed", "open"]:
                    raise PermissionDeniedException("Customers can only close, resolve, or reopen tickets.")

            old_status = ticket.status
            ticket.status = data.status
            now = utcnow()

            if data.status in ("resolved", "closed") and not ticket.resolved_at:
                ticket.resolved_at = now
            if data.status == "closed" and not ticket.closed_at:
                ticket.closed_at = now
            elif data.status in ["open", "in_progress"] and old_status in ["resolved", "closed"]:
                ticket.resolved_at = None
                ticket.closed_at = None

            sys_msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role="system",
                message_type="action_card",
                content=f"Ticket status changed from '{old_status}' to '{ticket.status}' by {current_user.full_name}",
            )
            session.add(sys_msg)
            await session.commit()
            await session.refresh(ticket)
            await session.refresh(sys_msg)

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=agent, app=app, ticket_type=ticket_type)

            # Tell the customer when their ticket is resolved or closed.
            notify_customer = ticket.status in ("resolved", "closed") and ticket.status != old_status
            await publish_ticket_event(
                ticket,
                resp,
                reason="status_changed",
                email_kind=notification_service.KIND_RESOLVED if notify_customer else None,
                actor_name=current_user.full_name,
                system_message=message_to_response(sys_msg),
            )
            return resp

    @patch("/{ticket_id:int}/assign")
    async def assign_ticket(self, request: Request, ticket_id: Annotated[int, PathParameter()], data: TicketAssignRequest) -> TicketResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can assign tickets.")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            target_agent = None
            if data.agent_id:
                target_agent = await session.get(User, data.agent_id)
                if not target_agent or target_agent.role not in ("agent", "admin"):
                    raise ValidationException("Assigned user must be staff.")
                ticket.assigned_agent_id = target_agent.id
                if ticket.status == "open":
                    ticket.status = "in_progress"
                assignee_name = target_agent.full_name
            else:
                ticket.assigned_agent_id = None
                if ticket.status == "in_progress":
                    ticket.status = "open"
                assignee_name = "Unassigned"

            sys_msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role="system",
                message_type="action_card",
                content=f"Ticket assigned to {assignee_name} by {current_user.full_name}",
            )
            session.add(sys_msg)
            await session.commit()
            await session.refresh(ticket)
            await session.refresh(sys_msg)

            customer = await session.get(User, ticket.customer_id)
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=target_agent, app=app, ticket_type=ticket_type)

            await publish_ticket_event(
                ticket,
                resp,
                reason="assignment_changed",
                email_kind=notification_service.KIND_ASSIGNED if target_agent else None,
                actor_name=current_user.full_name,
                system_message=message_to_response(sys_msg),
            )
            return resp

    @patch("/{ticket_id:int}/priority")
    async def update_priority(self, request: Request, ticket_id: Annotated[int, PathParameter()], data: TicketPriorityUpdateRequest) -> TicketResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("agent", "admin"):
            raise PermissionDeniedException("Forbidden: Only support staff can update ticket priority.")

        valid_priorities = ["low", "medium", "high", "urgent"]
        if data.priority not in valid_priorities:
            raise ValidationException(f"Invalid priority: {data.priority}")

        async with async_session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if not ticket:
                raise NotFoundException("Ticket not found.")

            old_priority = ticket.priority
            ticket.priority = data.priority

            if not ticket.first_responded_at:
                first_due, res_due = calculate_sla_deadlines(ticket.priority, ticket.created_at)
                ticket.first_response_due_at = first_due
                ticket.resolution_due_at = res_due
            elif not ticket.resolved_at:
                _, res_due = calculate_sla_deadlines(ticket.priority, ticket.created_at)
                ticket.resolution_due_at = res_due

            sys_msg = Message(
                ticket_id=ticket.id,
                sender_id=current_user.id,
                sender_name=current_user.full_name,
                sender_role="system",
                message_type="action_card",
                content=f"Priority updated from {old_priority.upper()} to {ticket.priority.upper()}",
            )
            session.add(sys_msg)
            await session.commit()
            await session.refresh(ticket)
            await session.refresh(sys_msg)

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=agent, app=app, ticket_type=ticket_type)

            await publish_ticket_event(
                ticket,
                resp,
                reason="priority_changed",
                actor_name=current_user.full_name,
                system_message=message_to_response(sys_msg),
            )
            return resp
