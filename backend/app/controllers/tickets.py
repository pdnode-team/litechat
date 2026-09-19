from datetime import datetime, timezone
import json
import secrets
import uuid
from typing import List, Optional
from litestar import Controller, get, post, patch, Request
from litestar.exceptions import (
    NotAuthorizedException,
    PermissionDeniedException,
    NotFoundException,
    ValidationException,
)
from sqlalchemy import select, or_, desc
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.user import User
from app.models.message import Message
from app.models.managed_app import ManagedApp
from app.models.ticket_type import TicketType
from app.schemas.ticket import (
    TicketCreate,
    TicketResponse,
    TicketStatusUpdateRequest,
    TicketAssignRequest,
    TicketPriorityUpdateRequest,
)
from app.schemas.auth import UserResponse
from app.controllers.auth import get_current_user_from_request
from app.controllers.managed_apps import app_to_response
from app.controllers.ticket_types import type_to_response
from app.services.sla_service import calculate_sla_deadlines, get_sla_status
from app.services.websocket_hub import hub

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

        now = datetime.now(timezone.utc)
        first_due, res_due = calculate_sla_deadlines(data.priority, now)

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

            # Validate optional app and ticket_type
            managed_app = None
            if data.app_id:
                managed_app = await session.get(ManagedApp, data.app_id)

            t_type = None
            if data.ticket_type_id:
                t_type = await session.get(TicketType, data.ticket_type_id)

            custom_fields_json = json.dumps(data.custom_fields) if data.custom_fields else "{}"

            ticket = Ticket(
                ticket_code=ticket_code,
                title=data.title.strip(),
                description=data.description.strip(),
                status="open",
                priority=data.priority,
                category=data.category,
                customer_id=current_user.id,
                app_id=data.app_id,
                target_url=data.target_url.strip() if data.target_url else None,
                ticket_type_id=data.ticket_type_id,
                custom_fields_json=custom_fields_json,
                first_response_due_at=first_due,
                resolution_due_at=res_due,
                tags=data.tags or "",
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
                content=data.description.strip(),
            )
            session.add(initial_msg)
            await session.commit()

            return build_ticket_response(
                ticket,
                customer=current_user,
                agent=None,
                app=managed_app,
                ticket_type=t_type,
            )

    @get("/")
    async def list_tickets(
        self,
        request: Request,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        assigned_to_me: Optional[bool] = None,
    ) -> List[TicketResponse]:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")

        async with async_session_factory() as session:
            stmt = select(Ticket).order_by(desc(Ticket.created_at))

            # Strictly enforce: Customers see ONLY their own tickets
            if current_user.role == "customer":
                stmt = stmt.where(Ticket.customer_id == current_user.id)
            elif assigned_to_me and current_user.role in ("agent", "admin"):
                stmt = stmt.where(Ticket.assigned_agent_id == current_user.id)

            if status:
                stmt = stmt.where(Ticket.status == status)
            if priority:
                stmt = stmt.where(Ticket.priority == priority)
            if category:
                stmt = stmt.where(Ticket.category == category)
            if search:
                term = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(
                        Ticket.title.ilike(term),
                        Ticket.ticket_code.ilike(term),
                        Ticket.description.ilike(term),
                    )
                )

            tickets_res = await session.execute(stmt)
            tickets = tickets_res.scalars().all()

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

            return [
                build_ticket_response(
                    t,
                    customer=users_map.get(t.customer_id),
                    agent=users_map.get(t.assigned_agent_id) if t.assigned_agent_id else None,
                    app=apps_map.get(t.app_id) if t.app_id else None,
                    ticket_type=types_map.get(t.ticket_type_id) if t.ticket_type_id else None,
                )
                for t in tickets
            ]

    @get("/{ticket_id:int}")
    async def get_ticket(self, request: Request, ticket_id: int) -> TicketResponse:
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

    @patch("/{ticket_id:int}/status")
    async def update_status(self, request: Request, ticket_id: int, data: TicketStatusUpdateRequest) -> TicketResponse:
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
            now = datetime.now(timezone.utc)

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

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=agent, app=app, ticket_type=ticket_type)

            await hub.broadcast(
                ticket.id,
                {"type": "ticket_updated", "ticket": resp.model_dump(mode="json")},
            )
            return resp

    @patch("/{ticket_id:int}/assign")
    async def assign_ticket(self, request: Request, ticket_id: int, data: TicketAssignRequest) -> TicketResponse:
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

            customer = await session.get(User, ticket.customer_id)
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=target_agent, app=app, ticket_type=ticket_type)

            await hub.broadcast(
                ticket.id,
                {"type": "ticket_updated", "ticket": resp.model_dump(mode="json")},
            )
            return resp

    @patch("/{ticket_id:int}/priority")
    async def update_priority(self, request: Request, ticket_id: int, data: TicketPriorityUpdateRequest) -> TicketResponse:
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

            customer = await session.get(User, ticket.customer_id)
            agent = await session.get(User, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
            app = await session.get(ManagedApp, ticket.app_id) if ticket.app_id else None
            ticket_type = await session.get(TicketType, ticket.ticket_type_id) if ticket.ticket_type_id else None
            resp = build_ticket_response(ticket, customer=customer, agent=agent, app=app, ticket_type=ticket_type)

            await hub.broadcast(
                ticket.id,
                {"type": "ticket_updated", "ticket": resp.model_dump(mode="json")},
            )
            return resp
