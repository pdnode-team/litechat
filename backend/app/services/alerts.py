"""Optional fire-and-forget webhook for 5xx failures.

Enabled only when ``ALERT_WEBHOOK_URL`` is set. Delivery is best-effort: a
timeout, a DNS failure or a 4xx from the receiver is logged and then ignored
so the original HTTP response is never affected.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import ALERT_WEBHOOK_URL

logger = logging.getLogger("litechat.alerts")

_TIMEOUT = httpx.Timeout(5.0)


async def _post_alert(payload: Dict[str, Any]) -> None:
    url = ALERT_WEBHOOK_URL
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "Alert webhook returned %s for event %s",
                    response.status_code,
                    payload.get("event"),
                )
    except Exception:
        logger.warning("Alert webhook failed", exc_info=True)


def schedule_alert(payload: Dict[str, Any]) -> None:
    """Queue a webhook POST on the running loop. Never raises."""
    if not ALERT_WEBHOOK_URL:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_post_alert(payload))
    except Exception:
        logger.warning("Could not schedule alert webhook", exc_info=True)


def server_error_payload(
    *,
    request_id: Optional[str],
    method: str,
    path: str,
    exception: BaseException,
) -> Dict[str, Any]:
    summary = f"{type(exception).__name__}: {exception}"
    if len(summary) > 500:
        summary = summary[:497] + "..."
    return {
        "event": "server_error",
        "request_id": request_id,
        "method": method,
        "path": path,
        "exception": summary,
    }
