from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from app.config import SLA_FIRST_RESPONSE_MINUTES, SLA_RESOLUTION_MINUTES
from app.db.base import utcnow

WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class SlaPolicy:
    first_response: dict[str, int]
    resolution: dict[str, int]
    business_hours_enabled: bool
    weekdays: tuple[int, ...]  # Monday=0
    start: time
    end: time
    timezone: str
    observe_holidays: bool

    @classmethod
    def from_settings(cls, values: dict) -> "SlaPolicy":
        first = {
            "urgent": int(values.get("sla_first_urgent") or SLA_FIRST_RESPONSE_MINUTES["urgent"]),
            "high": int(values.get("sla_first_high") or SLA_FIRST_RESPONSE_MINUTES["high"]),
            "medium": int(values.get("sla_first_medium") or SLA_FIRST_RESPONSE_MINUTES["medium"]),
            "low": int(values.get("sla_first_low") or SLA_FIRST_RESPONSE_MINUTES["low"]),
        }
        resolution = {
            "urgent": int(values.get("sla_resolution_urgent") or SLA_RESOLUTION_MINUTES["urgent"]),
            "high": int(values.get("sla_resolution_high") or SLA_RESOLUTION_MINUTES["high"]),
            "medium": int(values.get("sla_resolution_medium") or SLA_RESOLUTION_MINUTES["medium"]),
            "low": int(values.get("sla_resolution_low") or SLA_RESOLUTION_MINUTES["low"]),
        }
        weekdays = _parse_weekdays(str(values.get("sla_weekdays") or "mon,tue,wed,thu,fri"))
        return cls(
            first_response=first,
            resolution=resolution,
            business_hours_enabled=bool(values.get("sla_business_hours_enabled")),
            weekdays=weekdays,
            start=_parse_clock(str(values.get("sla_start") or "09:00")),
            end=_parse_clock(str(values.get("sla_end") or "18:00")),
            timezone=str(values.get("sla_timezone") or "UTC"),
            observe_holidays=bool(values.get("sla_observe_holidays")),
        )


def _parse_weekdays(raw: str) -> tuple[int, ...]:
    found: list[int] = []
    for part in raw.lower().replace(" ", "").split(","):
        if not part:
            continue
        if part.isdigit():
            idx = int(part)
            if 0 <= idx <= 6:
                found.append(idx)
        elif part in WEEKDAY_NAMES:
            found.append(WEEKDAY_NAMES.index(part))
    return tuple(found or (0, 1, 2, 3, 4))


def _parse_clock(raw: str) -> time:
    try:
        hours, minutes = raw.strip().split(":")[:2]
        return time(int(hours) % 24, int(minutes) % 60)
    except (TypeError, ValueError):
        return time(9, 0)


def _tz(name: str) -> timezone | ZoneInfo:
    if not name or name.upper() == "UTC":
        return timezone.utc
    if name in ("UTC+8", "GMT+8"):
        name = "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        if name in ("Asia/Shanghai", "Asia/Hong_Kong"):
            return timezone(timedelta(hours=8))
        return timezone.utc


def _localize(moment: datetime, tzinfo) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tzinfo)


def _is_open(moment: datetime, policy: SlaPolicy) -> bool:
    if moment.weekday() not in policy.weekdays:
        return False
    clock = moment.timetz().replace(tzinfo=None)
    if policy.start == policy.end:
        return True
    if policy.start < policy.end:
        return policy.start <= clock < policy.end
    return clock >= policy.start or clock < policy.end


def _next_open(moment: datetime, policy: SlaPolicy) -> datetime:
    cursor = moment.replace(second=0, microsecond=0)
    if _is_open(cursor, policy):
        return cursor
    for _ in range(14 * 24 * 60):
        cursor += timedelta(minutes=1)
        if _is_open(cursor, policy):
            return cursor
    return moment + timedelta(days=1)


def add_business_minutes(start: datetime, minutes: int, policy: SlaPolicy) -> datetime:
    """Advance ``minutes`` of open time. Result is naive UTC."""
    if minutes <= 0:
        return start if start.tzinfo is None else start.astimezone(timezone.utc).replace(tzinfo=None)
    if not policy.business_hours_enabled:
        due = start + timedelta(minutes=minutes)
        return due if due.tzinfo is None else due.astimezone(timezone.utc).replace(tzinfo=None)

    tzinfo = _tz(policy.timezone)
    cursor = _next_open(_localize(start, tzinfo), policy)
    remaining = minutes
    guard = 0
    while remaining > 0 and guard < 20_000:
        guard += 1
        if not _is_open(cursor, policy):
            cursor = _next_open(cursor, policy)
            continue
        cursor += timedelta(minutes=1)
        remaining -= 1
    return cursor.astimezone(timezone.utc).replace(tzinfo=None)


async def load_policy() -> SlaPolicy:
    from app.services import settings_service

    return SlaPolicy.from_settings(await settings_service.get_all())


async def calculate_sla_deadlines(
    priority: str,
    start_time: Optional[datetime] = None,
    policy: Optional[SlaPolicy] = None,
) -> Tuple[datetime, datetime]:
    """Deadlines are naive UTC, matching the columns they are stored in."""
    start = start_time or utcnow()
    active = policy or await load_policy()
    key = priority.lower()
    first_mins = active.first_response.get(key, active.first_response["medium"])
    resolution_mins = active.resolution.get(key, active.resolution["medium"])
    return (
        add_business_minutes(start, first_mins, active),
        add_business_minutes(start, resolution_mins, active),
    )


def get_sla_status(
    due_at: Optional[datetime],
    completed_at: Optional[datetime] = None,
) -> str:
    if not due_at:
        return "on_track"

    now = utcnow()
    if completed_at:
        return "fulfilled" if completed_at <= due_at else "breached"

    if now > due_at:
        return "breached"

    return "on_track"
