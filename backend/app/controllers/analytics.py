from typing import Dict, List
from litestar import Controller, get, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.ticket import Ticket
from app.models.user import User
from app.models.csat_rating import CSATRating
from app.schemas.analytics import AnalyticsSummaryResponse, AgentPerformanceItem
from app.controllers.auth import get_current_user_from_request
from app.services.sla_service import get_sla_status

class AnalyticsController(Controller):
    path = "/api/analytics"

    @get("/summary")
    async def get_summary(self, request: Request) -> AnalyticsSummaryResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role not in ("admin", "agent"):
            raise PermissionDeniedException("Forbidden: Only support staff can access analytics.")

        async with async_session_factory() as session:
            # 1. Fetch all tickets
            tickets_stmt = select(Ticket)
            tickets = (await session.execute(tickets_stmt)).scalars().all()

            status_counts = {"open": 0, "pending": 0, "in_progress": 0, "resolved": 0, "closed": 0}
            category_counts = {}
            priority_counts = {}
            breached_count = 0
            resolved_or_closed_count = 0
            sla_fulfilled_count = 0

            for t in tickets:
                status_counts[t.status] = status_counts.get(t.status, 0) + 1
                category_counts[t.category] = category_counts.get(t.category, 0) + 1
                priority_counts[t.priority] = priority_counts.get(t.priority, 0) + 1

                sla_res = get_sla_status(t.resolution_due_at, t.resolved_at)
                if sla_res == "breached":
                    breached_count += 1
                elif sla_res == "fulfilled":
                    sla_fulfilled_count += 1

                if t.status in ("resolved", "closed"):
                    resolved_or_closed_count += 1

            sla_rate = (
                round((sla_fulfilled_count / resolved_or_closed_count) * 100, 1)
                if resolved_or_closed_count > 0
                else None
            )

            # 2. CSAT ratings
            csat_stmt = select(CSATRating)
            ratings = (await session.execute(csat_stmt)).scalars().all()
            total_reviews = len(ratings)
            csat_avg = (
                round(sum(r.score for r in ratings) / total_reviews, 1)
                if total_reviews > 0
                else None
            )

            # 3. Agent Performance
            agents_stmt = select(User).where(User.role.in_(["agent", "admin"]))
            agents = (await session.execute(agents_stmt)).scalars().all()

            agent_perf_list: List[AgentPerformanceItem] = []
            for ag in agents:
                ag_tickets = [t for t in tickets if t.assigned_agent_id == ag.id]
                assigned_count = len(ag_tickets)
                resolved_tickets = [t for t in ag_tickets if t.status in ("resolved", "closed") and t.resolved_at]
                resolved_count = len(resolved_tickets)

                durations = []
                for t in resolved_tickets:
                    diff_mins = (t.resolved_at - t.created_at).total_seconds() / 60.0
                    durations.append(max(diff_mins, 1.0))
                avg_time = round(sum(durations) / len(durations), 1) if durations else 0.0

                ag_ticket_ids = {t.id for t in ag_tickets}
                ag_ratings = [r.score for r in ratings if r.ticket_id in ag_ticket_ids]
                ag_csat = round(sum(ag_ratings) / len(ag_ratings), 1) if ag_ratings else None

                agent_perf_list.append(
                    AgentPerformanceItem(
                        agent_id=ag.id,
                        name=ag.full_name,
                        assigned_count=assigned_count,
                        resolved_count=resolved_count,
                        avg_resolution_time_minutes=avg_time,
                        csat_avg=ag_csat,
                    )
                )

            return AnalyticsSummaryResponse(
                total_tickets=len(tickets),
                open_tickets=status_counts.get("open", 0),
                pending_tickets=status_counts.get("pending", 0),
                in_progress_tickets=status_counts.get("in_progress", 0),
                resolved_tickets=status_counts.get("resolved", 0),
                closed_tickets=status_counts.get("closed", 0),
                sla_compliance_rate=sla_rate,
                sla_breached_count=breached_count,
                csat_average_score=csat_avg,
                csat_total_reviews=total_reviews,
                category_distribution=category_counts,
                priority_distribution=priority_counts,
                agents_performance=agent_perf_list,
            )
