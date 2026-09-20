"""Turn database constraint failures into errors a client can act on.

A duplicate value reaches the API as an ``IntegrityError`` whose only reliable
description is the constraint name: PostgreSQL says
``duplicate key value violates unique constraint "ix_managed_apps_code"`` while
SQLite says ``UNIQUE constraint failed: managed_apps.code``. Matching on it lets
the controller answer 422 instead of 500 without *guessing* why the insert failed.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("litechat.db")


def is_unique_violation(error: IntegrityError, hints: Iterable[str]) -> bool:
    """True when ``error`` is a duplicate-key failure on one of ``hints``.

    A primary-key / sequence collision is deliberately *not* matched here: that
    is a different problem (a sequence that drifted out of sync with the table)
    which needs a different fix, and reporting it to the user as "this code
    already exists" would send them chasing the wrong thing.
    """
    message = str(getattr(error, "orig", error))
    return any(hint in message for hint in hints)
