"""Append-only audit trail. Failures here must never fail the business action."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.db.session import async_session_factory
from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger("litechat.audit")

_REDACT_KEYS = {
    "password",
    "current_password",
    "new_password",
    "hashed_password",
    "smtp_password",
    "token",
    "access_token",
    "jwt",
}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in _REDACT_KEYS:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _scrub(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(_scrub(value), default=str)[:8000]


async def record(
    *,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Any = None,
    before: Any = None,
    after: Any = None,
    meta: Any = None,
) -> None:
    try:
        async with async_session_factory() as session:
            session.add(
                AuditLog(
                    actor_id=actor.id if actor else None,
                    actor_name=(actor.full_name if actor else "system")[:150],
                    action=action[:80],
                    entity_type=entity_type[:80],
                    entity_id=None if entity_id is None else str(entity_id)[:80],
                    before_json=_dump(before),
                    after_json=_dump(after),
                    meta_json=_dump(meta),
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to write audit log action=%s entity=%s", action, entity_type)
