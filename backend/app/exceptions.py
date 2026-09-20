"""Application exceptions that carry machine readable detail to the client."""
from __future__ import annotations

from typing import Optional, Sequence

from litestar.exceptions import ValidationException
from litestar.status_codes import HTTP_422_UNPROCESSABLE_ENTITY

from app.services.form_logic import FieldError

MAX_SUMMARY_LENGTH = 300


def summarise(errors: Sequence[FieldError]) -> str:
    """One line a human can read in a banner above the form."""
    if not errors:
        return "The request was rejected."
    if len(errors) == 1:
        return errors[0].message

    joined = " ".join(error.message for error in errors[:3])
    if len(errors) > 3:
        joined += f" (+{len(errors) - 3} more)"
    return joined[:MAX_SUMMARY_LENGTH]


class FormValidationError(ValidationException):
    """A 422 whose body carries one entry per rejected input.

    The frontend reads ``errors[]`` to attach each message to the input that
    caused it, so the detail is never collapsed into a single opaque string.
    """

    def __init__(self, errors: Sequence[FieldError], detail: Optional[str] = None) -> None:
        self.errors = list(errors)
        super().__init__(
            detail=detail or summarise(self.errors),
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            extra=[error.as_dict() for error in self.errors],
        )
