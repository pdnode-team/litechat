"""Uniform error responses and detailed logging for unhandled failures.

Two responsibilities, both about the same problem - a client that only sees
"500 Internal Server Error" while the operator needs the stack trace:

* every rejected input leaves through :func:`validation_exception_handler` as
  ``{"detail": ..., "errors": [{"field", "label", "message", "code"}]}`` so the
  form can point at the exact input;
* anything unexpected is logged with a full traceback, the request id, the route
  and the caller, and answered with a short message that repeats the request id.
  Grep the request id in the server log to get from a user report to the traceback.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from litestar import Request, Response
from litestar.exceptions import ValidationException
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.config import IS_PRODUCTION
from app.logging_config import current_request_id

logger = logging.getLogger("litechat.errors")


def _client_ip(request: Request) -> str:
    try:
        client = request.scope.get("client")
    except AttributeError:  # pragma: no cover - defensive
        return "-"
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "-"


def _normalise_field_errors(extra: Any) -> List[Dict[str, str]]:
    """Accept both our own payload and Litestar's request-validation payload."""
    if not isinstance(extra, (list, tuple)):
        return []

    normalised: List[Dict[str, str]] = []
    for item in extra:
        if not isinstance(item, dict):
            continue

        field = item.get("field") or item.get("key") or "body"
        message = str(item.get("message") or item.get("detail") or "").strip()

        if not message:
            # Pydantic v2 style: {"loc": ["body", "title"], "msg": "..."}
            location = item.get("loc")
            if isinstance(location, (list, tuple)) and location:
                parts: Sequence[Any] = [part for part in location if part not in ("body",)]
                if parts:
                    field = ".".join(str(part) for part in parts)
            message = str(item.get("msg") or "").strip()

        if not message:
            message = str(item)

        normalised.append(
            {
                "field": str(field),
                "label": str(item.get("label") or ""),
                "message": message,
                "code": str(item.get("code") or "invalid"),
            }
        )
    return normalised


def validation_exception_handler(request: Request, exc: ValidationException) -> Response:
    """Return every rejected input at once, addressed by field."""
    errors = _normalise_field_errors(exc.extra)
    status = exc.status_code or HTTP_422_UNPROCESSABLE_ENTITY

    if errors:
        # Our own FormValidationError already carries a human summary. Litestar's
        # request validation does not - its detail is "Validation failed for
        # POST /api/tickets", which says nothing to the person filling the form.
        from app.exceptions import FormValidationError

        detail = exc.detail if isinstance(exc, FormValidationError) else errors[0]["message"]
    else:
        detail = exc.detail

    content: Dict[str, Any] = {
        "status_code": status,
        "detail": detail,
    }
    if errors:
        content["errors"] = errors

    return Response(
        content=content,
        status_code=status,
        headers=exc.headers,
    )


def server_error_handler(request: Request, exc: Exception) -> Response:
    """Log the failure with everything needed to debug it, answer with a reference."""
    request_id = current_request_id()

    # The request body is deliberately not logged: it may hold a password, a
    # reset token or a file payload. Method, route, query and headers are enough
    # to reproduce a failure, and the traceback points at the actual line.
    logger.error(
        "Unhandled %s on %s %s%s (request_id=%s, ip=%s, user_agent=%r): %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        f"?{request.url.query}" if request.url.query else "",
        request_id,
        _client_ip(request),
        request.headers.get("user-agent", "-"),
        exc,
        exc_info=exc,
    )

    try:
        from app.services.alerts import schedule_alert, server_error_payload

        schedule_alert(
            server_error_payload(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                exception=exc,
            )
        )
    except Exception:
        logger.warning("Failed to schedule 5xx alert", exc_info=True)

    if IS_PRODUCTION:
        detail = f"Something went wrong on our side. Reference: {request_id}"
    else:
        # Local development keeps the real message on screen; production never
        # leaks internals to a customer.
        detail = f"{type(exc).__name__}: {exc} (reference {request_id})"

    return Response(
        content={
            "status_code": HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": detail,
            "request_id": request_id,
        },
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
    )


def internal_server_exception_handler(request: Request, exc: Exception) -> Response:
    return server_error_handler(request, exc)


# Registered by *status code*, not by exception class. Litestar resolves a
# numeric key first and only then walks the exception's MRO; registering
# `Exception` directly would swallow every business 4xx (404, 403, 401, ...)
# because `Exception` is in their MRO too.
#
# 400 covers Litestar's own request-schema validation (it raises
# ValidationException, whose default status is 400) so body-schema failures and
# our semantic failures arrive in exactly the same shape.
EXCEPTION_HANDLERS: Dict[Any, Any] = {
    HTTP_400_BAD_REQUEST: validation_exception_handler,
    HTTP_422_UNPROCESSABLE_ENTITY: validation_exception_handler,
    HTTP_500_INTERNAL_SERVER_ERROR: internal_server_exception_handler,
}
