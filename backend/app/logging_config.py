"""Central logging configuration.

Every log line the application writes goes to stdout with a timestamp, a level,
the logger name and the id of the HTTP request that produced it, for example::

    2026-02-11 09:14:03 | ERROR    | litechat.errors | 5f3a91c2 | Unhandled error POST /api/tickets

That request id is also returned to the client (response header ``X-Request-ID``
and, for a 500, in the body), which is what makes a user-reported failure findable
in the server output.

In a container platform (Dokploy, Docker, systemd) stdout is the durable log, so
that is the default sink. Set ``LOG_FILE`` to also mirror everything into a
rotating file when running somewhere without log collection.
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Names whose chatter is not useful at INFO level in production.
NOISY_LOGGERS = {
    "sqlalchemy.engine": logging.WARNING,
    "aiosqlite": logging.WARNING,
    "asyncpg": logging.WARNING,
    "httpx": logging.INFO,
    "httpcore": logging.WARNING,
    "multipart": logging.WARNING,
    "python_multipart": logging.WARNING,
    "markdown_it": logging.WARNING,
}

_request_id: ContextVar[str] = ContextVar("litechat_request_id", default="-")


def current_request_id() -> str:
    """Request id of the HTTP request being handled (``-`` outside a request)."""
    return _request_id.get()


def set_request_id(value: str) -> Token:
    return _request_id.set(value)


def reset_request_id(token: Token) -> None:
    try:
        _request_id.reset(token)
    except ValueError:  # pragma: no cover - only when crossing async contexts
        _request_id.set("-")


class RequestIdFilter(logging.Filter):
    """Stamp every record with the current request id so the format can use it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = _request_id.get()
        return True


_original_record_factory = logging.getLogRecordFactory()
_record_factory_installed = False


def _request_id_record_factory(*args, **kwargs) -> logging.LogRecord:
    """Stamp the id on the record itself, not just on our handler.

    A handler filter would only cover our own handler: a record captured by
    anything else (a test harness, a future third-party handler) would be missing
    the attribute entirely. Setting it on the record makes the id available
    wherever the record ends up.
    """
    record = _original_record_factory(*args, **kwargs)
    if not hasattr(record, "request_id"):
        record.request_id = _request_id.get()
    return record


def _install_record_factory() -> None:
    global _record_factory_installed
    if _record_factory_installed:
        return
    logging.setLogRecordFactory(_request_id_record_factory)
    _record_factory_installed = True


def _resolve_level(raw: Optional[str]) -> int:
    if not raw:
        return logging.INFO
    level = logging.getLevelName(raw.strip().upper())
    return level if isinstance(level, int) else logging.INFO


def configure_logging() -> None:
    """Install the handlers used by the whole process. Safe to call twice."""
    level = _resolve_level(os.getenv("LOG_LEVEL"))
    _install_record_factory()
    # uvicorn configures logging before it imports the application, so at this
    # point `uvicorn` already owns its own handlers. Only the root logger is
    # rebuilt here; uvicorn's own records keep their format.
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RequestIdFilter())
    root.addHandler(stream_handler)

    log_file = os.getenv("LOG_FILE")
    if log_file:
        try:
            # The file handler is for operators who cannot rely on stdout; it is
            # duplicated on purpose so a container restart never loses the tail.
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(RequestIdFilter())
            root.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - depends on the host
            root.warning("Could not open LOG_FILE %r: %s", log_file, exc)

    root.setLevel(level)

    for name, noisy_level in NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(max(level, noisy_level))

    # The application writes its own access line (with a request id and a
    # duration) from RequestContextMiddleware, so uvicorn's duplicate access log
    # is silenced unless the operator explicitly asks for it.
    if os.getenv("UVICORN_ACCESS_LOG", "").strip().lower() not in ("1", "true", "yes", "on"):
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger("litechat").info(
        "Logging configured (level=%s, file=%s)", logging.getLevelName(level), log_file or "stdout only"
    )
