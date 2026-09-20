"""Conditional logic and server-side validation for dynamic ticket forms.

This module is the authoritative implementation: the browser runs a mirrored
version (``frontend/src/utils/formLogic.ts``) purely to give immediate feedback,
but every rule is enforced again here because the client can be bypassed. The two
implementations are intentionally kept structurally identical - if you change a
rule in one, change it in the other.

Evaluation order matters and is well defined: conditions may only reference
fields defined *above* the field that declares them, so a single forward pass is
enough. A field whose condition is false is dropped from the submission entirely,
which is what makes hidden answers impossible to smuggle in.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from app.schemas.ticket_type import ConditionGroup, CustomFieldDefinition

# --- Limits ------------------------------------------------------------------
MAX_CUSTOM_FIELDS = 50
MAX_MULTI_SELECT_ITEMS = 50
# Length cap applied to an "Other" answer (and to any free-form select value).
MAX_OTHER_LENGTH = 255
FIELD_TYPE_MAX_LENGTH: Dict[str, int] = {
    "text": 500,
    "textarea": 5000,
    "url": 500,
    "date": 10,
    "select": MAX_OTHER_LENGTH,
}

MIN_TITLE_LENGTH = 3
MAX_TITLE_LENGTH = 255
MIN_DESCRIPTION_LENGTH = 5
MAX_DESCRIPTION_LENGTH = 20000
MAX_TAGS_LENGTH = 500
MAX_TARGET_URL_LENGTH = 500
# Upper bound on the serialised answers, so one submission cannot bloat a row.
MAX_CUSTOM_FIELDS_JSON_BYTES = 32 * 1024

BASE_CATEGORIES = ("technical", "billing", "account", "general")
BASE_PRIORITIES = ("low", "medium", "high", "urgent")

CUSTOM_FIELD_PREFIX = "custom_fields."


@dataclass(frozen=True)
class FieldError:
    """One rejected input, addressed at the exact input that caused it."""

    field: str
    message: str
    label: str = ""
    code: str = "invalid"

    def as_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "label": self.label,
            "message": self.message,
            "code": self.code,
        }


# --- Value helpers -----------------------------------------------------------

def is_blank(value: Any) -> bool:
    """True when the answer carries no information (and may not satisfy `required`)."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, bool):
        # An explicit "No" is an answer, not a missing value.
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return False
    return False


def _light_normalise(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_light_normalise(item) for item in value]
    return value


def _to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "on", "1"):
            return True
        if text in ("false", "no", "off", "0", ""):
            return False
    return None


def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
    return None


def _as_items(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _scalar_equals(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        left, right = _to_bool(actual), _to_bool(expected)
        if left is not None and right is not None:
            return left is right or left == right
    left_num, right_num = _to_number(actual), _to_number(expected)
    if left_num is not None and right_num is not None:
        return left_num == right_num
    if actual is None or expected is None:
        return actual is None and expected is None
    return str(actual).strip().lower() == str(expected).strip().lower()


def _matches_scalar(actual: Any, expected: Any) -> bool:
    """Equality where the answer itself may be a multi-select list."""
    if isinstance(actual, (list, tuple, set, frozenset)):
        return any(_scalar_equals(item, expected) for item in actual)
    return _scalar_equals(actual, expected)


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple, set, frozenset)):
        return any(_contains(item, expected) for item in actual)
    if actual is None or expected is None:
        return False
    return str(expected).strip().lower() in str(actual).strip().lower()


def _compare_numeric(actual: Any, expected: Any, operators: Sequence[str]) -> bool:
    left, right = _to_number(actual), _to_number(expected)
    if left is None or right is None:
        return False
    if "gt" in operators and left > right:
        return True
    if "gte" in operators and left >= right:
        return True
    if "lt" in operators and left < right:
        return True
    if "lte" in operators and left <= right:
        return True
    return False


# --- Conditions --------------------------------------------------------------

def condition_matches(condition: Any, values: Mapping[str, Any]) -> bool:
    """Evaluate a single condition against the current answers."""
    field = getattr(condition, "field", None) or (condition.get("field") if isinstance(condition, dict) else None)
    if not field:
        return True
    operator = getattr(condition, "operator", None) or (
        condition.get("operator") if isinstance(condition, dict) else "equals"
    )
    expected = getattr(condition, "value", None) if not isinstance(condition, dict) else condition.get("value")
    actual = values.get(field)

    if operator == "is_answered":
        return not is_blank(actual)
    if operator == "is_empty":
        return is_blank(actual)
    if operator == "equals":
        if isinstance(expected, (list, tuple, set, frozenset)):
            return any(_matches_scalar(actual, item) for item in expected)
        return _matches_scalar(actual, expected)
    if operator == "not_equals":
        if isinstance(expected, (list, tuple, set, frozenset)):
            return not any(_matches_scalar(actual, item) for item in expected)
        return not _matches_scalar(actual, expected)
    if operator == "contains":
        return _contains(actual, expected)
    if operator == "not_contains":
        return not _contains(actual, expected)
    if operator == "in":
        items = expected if isinstance(expected, (list, tuple, set, frozenset)) else [expected]
        return any(_matches_scalar(actual, item) for item in items)
    if operator == "not_in":
        items = expected if isinstance(expected, (list, tuple, set, frozenset)) else [expected]
        return not any(_matches_scalar(actual, item) for item in items)
    if operator == "gt":
        return _compare_numeric(actual, expected, ("gt",))
    if operator == "gte":
        return _compare_numeric(actual, expected, ("gt", "gte"))
    if operator == "lt":
        return _compare_numeric(actual, expected, ("lt",))
    if operator == "lte":
        return _compare_numeric(actual, expected, ("lt", "lte"))
    return True


def group_matches(group: Optional[ConditionGroup], values: Mapping[str, Any]) -> bool:
    """Evaluate an all/any condition group. A missing group always matches."""
    if group is None:
        return True
    conditions = getattr(group, "conditions", None) or []
    if not conditions:
        return True
    results = (condition_matches(condition, values) for condition in conditions)
    if getattr(group, "logic", "all") == "any":
        return any(results)
    return all(results)


@dataclass
class FormEvaluation:
    """Result of one forward pass over a form schema."""

    visible: List[CustomFieldDefinition]
    hidden_keys: List[str]
    values: Dict[str, Any]

    @property
    def visible_keys(self) -> List[str]:
        return [field.key for field in self.visible]


def evaluate_form(
    schema: Sequence[CustomFieldDefinition],
    raw_values: Optional[Mapping[str, Any]],
) -> FormEvaluation:
    """Resolve which fields are visible and with which answers.

    Visibility is decided against the answers collected so far, so hiding a
    field automatically hides everything that depended on it.
    """
    source = dict(raw_values or {})
    values: Dict[str, Any] = {key: _light_normalise(value) for key, value in source.items()}

    visible: List[CustomFieldDefinition] = []
    hidden: List[str] = []
    effective: Dict[str, Any] = {}
    for field in schema:
        if group_matches(field.visible_when, effective):
            visible.append(field)
            effective[field.key] = values.get(field.key)
        else:
            hidden.append(field.key)

    return FormEvaluation(visible=visible, hidden_keys=hidden, values=values)


def is_field_visible(field: CustomFieldDefinition, values: Mapping[str, Any]) -> bool:
    return group_matches(field.visible_when, values)


def is_field_required(field: CustomFieldDefinition, values: Mapping[str, Any]) -> bool:
    if field.required:
        return True
    return field.required_when is not None and group_matches(field.required_when, values)


# --- Field level validation --------------------------------------------------

def _error(field: CustomFieldDefinition, message: str, code: str = "invalid") -> FieldError:
    return FieldError(
        field=f"{CUSTOM_FIELD_PREFIX}{field.key}",
        message=message,
        label=field.label,
        code=code,
    )


def _constraint_error(field: CustomFieldDefinition, generated: str, code: str) -> FieldError:
    """Constraint failures can carry an administrator supplied message."""
    return _error(field, field.error_message or generated, code)


def _check_length(field: CustomFieldDefinition, text: str) -> Optional[FieldError]:
    default_max = FIELD_TYPE_MAX_LENGTH.get(field.type, 500)
    minimum = field.min_length or 0
    maximum = field.max_length or default_max
    if len(text) < minimum:
        return _constraint_error(
            field,
            f"{field.label} must be at least {minimum} characters.",
            "too_short",
        )
    if len(text) > maximum:
        return _constraint_error(
            field,
            f"{field.label} must be at most {maximum} characters.",
            "too_long",
        )
    return None


def _validate_text_like(field: CustomFieldDefinition, value: Any) -> Tuple[Any, Optional[FieldError]]:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None, _error(field, f"{field.label} must be text.")
    text = str(value).strip()

    length_error = _check_length(field, text)
    if length_error:
        return None, length_error

    if field.pattern:
        try:
            if not re.fullmatch(field.pattern, text):
                return None, _constraint_error(
                    field,
                    f"{field.label} has an invalid format.",
                    "pattern_mismatch",
                )
        except re.error:
            # A broken pattern must not lock customers out of the form; the admin
            # endpoint rejects invalid patterns, so this is a last-resort guard.
            pass

    if field.type == "url":
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None, _error(
                field,
                f"{field.label} must be a full URL starting with http:// or https://",
                "invalid_url",
            )
    if field.type == "date":
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None, _error(
                field,
                f"{field.label} must be a date in YYYY-MM-DD format.",
                "invalid_date",
            )
    return text, None


def _validate_number(field: CustomFieldDefinition, value: Any) -> Tuple[Any, Optional[FieldError]]:
    number = _to_number(value)
    if number is None:
        return None, _constraint_error(field, f"{field.label} must be a number.", "not_a_number")
    if field.min_value is not None and number < field.min_value:
        return None, _constraint_error(
            field,
            f"{field.label} must be at least {_format_number(field.min_value)}.",
            "too_small",
        )
    if field.max_value is not None and number > field.max_value:
        return None, _constraint_error(
            field,
            f"{field.label} must be at most {_format_number(field.max_value)}.",
            "too_large",
        )
    if number.is_integer() and abs(number) < 1e15:
        return int(number), None
    return number, None


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _validate_switch(field: CustomFieldDefinition, value: Any) -> Tuple[Any, Optional[FieldError]]:
    boolean = _to_bool(value)
    if boolean is None:
        return None, _error(field, f"{field.label} must be yes or no.")
    return boolean, None


def _option_list_message(field: CustomFieldDefinition) -> str:
    shown = field.options[:8]
    listing = ", ".join(shown)
    if len(field.options) > len(shown):
        listing += ", ..."
    return f"{field.label} must be one of: {listing}"


def _validate_select(field: CustomFieldDefinition, value: Any) -> Tuple[Any, Optional[FieldError]]:
    if isinstance(value, (list, tuple, set, frozenset)) or isinstance(value, bool):
        return None, _error(field, f"{field.label} must be a single choice.")
    text = str(value).strip()
    if text in field.options:
        return text, None
    if field.allow_other:
        if len(text) > MAX_OTHER_LENGTH:
            return None, _error(
                field,
                f"{field.label}: a custom answer must be at most {MAX_OTHER_LENGTH} characters.",
                "too_long",
            )
        return text, None
    return None, _error(field, _option_list_message(field), "not_an_option")


def _validate_multi_select(field: CustomFieldDefinition, value: Any) -> Tuple[Any, Optional[FieldError]]:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return None, _error(field, f"{field.label} must be a list of choices.")
    items = _as_items(value)

    if len(items) > MAX_MULTI_SELECT_ITEMS:
        return None, _error(
            field,
            f"{field.label} accepts at most {MAX_MULTI_SELECT_ITEMS} choices.",
            "too_many_choices",
        )

    selected: List[str] = []
    custom: List[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in field.options:
            if text not in selected:
                selected.append(text)
        elif field.allow_other:
            if len(text) > MAX_OTHER_LENGTH:
                return None, _error(
                    field,
                    f"{field.label}: a custom answer must be at most {MAX_OTHER_LENGTH} characters.",
                    "too_long",
                )
            custom.append(text)
        else:
            return None, _error(field, _option_list_message(field), "not_an_option")

    if len(custom) > 1:
        return None, _error(
            field,
            f"{field.label} accepts a single custom answer.",
            "too_many_custom_answers",
        )

    for text in custom:
        if text not in selected:
            selected.append(text)
    return selected, None


FIELD_VALIDATORS = {
    "text": _validate_text_like,
    "textarea": _validate_text_like,
    "url": _validate_text_like,
    "date": _validate_text_like,
    "number": _validate_number,
    "switch": _validate_switch,
    "select": _validate_select,
    "multi_select": _validate_multi_select,
}


def validate_custom_fields(
    schema: Sequence[CustomFieldDefinition],
    raw_values: Optional[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], List[FieldError]]:
    """Validate submitted answers against a ticket type's schema.

    Returns the cleaned answers (visible fields only) plus every problem found,
    so the client can highlight all of them at once instead of one per attempt.
    """
    errors: List[FieldError] = []

    if raw_values is None:
        raw_values = {}
    if not isinstance(raw_values, Mapping):
        return {}, [FieldError("custom_fields", "Custom fields must be an object.", "Custom fields", "invalid")]

    raw = dict(raw_values)
    if len(raw) > MAX_CUSTOM_FIELDS:
        return {}, [
            FieldError(
                "custom_fields",
                f"A ticket accepts at most {MAX_CUSTOM_FIELDS} custom fields.",
                "Custom fields",
                "too_many_fields",
            )
        ]

    if not schema:
        if raw:
            return {}, [
                FieldError(
                    "custom_fields",
                    "This ticket type does not accept custom fields.",
                    "Custom fields",
                    "unexpected_fields",
                )
            ]
        return {}, []

    known_keys = {field.key for field in schema}
    for key in raw:
        if key not in known_keys:
            errors.append(
                FieldError(
                    f"{CUSTOM_FIELD_PREFIX}{key}",
                    f"Unknown field '{key}' for this ticket type.",
                    str(key),
                    "unknown_field",
                )
            )

    evaluation = evaluate_form(schema, raw)
    cleaned: Dict[str, Any] = {}

    for field in evaluation.visible:
        value = evaluation.values.get(field.key)

        if is_blank(value):
            if is_field_required(field, evaluation.values):
                errors.append(_error(field, f"{field.label} is required.", "required"))
            continue

        validator = FIELD_VALIDATORS.get(field.type, _validate_text_like)
        normalised, error = validator(field, value)
        if error is not None:
            errors.append(error)
            continue

        # A required multi-select must not end up empty after cleaning.
        if is_blank(normalised):
            if is_field_required(field, evaluation.values):
                errors.append(_error(field, f"{field.label} is required.", "required"))
            continue

        cleaned[field.key] = normalised

    return cleaned, errors


# --- Base (built-in) fields --------------------------------------------------

def validate_base_fields(
    *,
    title: Any,
    description: Any,
    tags: Any = "",
    target_url: Any = None,
    category: Any = "general",
    priority: Any = "medium",
) -> Tuple[Dict[str, Any], List[FieldError]]:
    """Validate and clean the built-in ticket fields.

    These are checked here rather than through Pydantic constraints so that every
    rejection reaches the client in one uniform, field-addressed shape.
    """
    errors: List[FieldError] = []

    clean_title = str(title or "").strip()
    if not clean_title:
        errors.append(FieldError("title", "A ticket subject is required.", "Ticket Subject", "required"))
    elif len(clean_title) < MIN_TITLE_LENGTH:
        errors.append(
            FieldError(
                "title",
                f"The ticket subject must be at least {MIN_TITLE_LENGTH} characters.",
                "Ticket Subject",
                "too_short",
            )
        )
    elif len(clean_title) > MAX_TITLE_LENGTH:
        errors.append(
            FieldError(
                "title",
                f"The ticket subject must be at most {MAX_TITLE_LENGTH} characters.",
                "Ticket Subject",
                "too_long",
            )
        )

    clean_description = str(description or "").strip()
    if not clean_description:
        errors.append(
            FieldError("description", "A description of the problem is required.", "Description", "required")
        )
    elif len(clean_description) < MIN_DESCRIPTION_LENGTH:
        errors.append(
            FieldError(
                "description",
                f"The description must be at least {MIN_DESCRIPTION_LENGTH} characters.",
                "Description",
                "too_short",
            )
        )
    elif len(clean_description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            FieldError(
                "description",
                f"The description must be at most {MAX_DESCRIPTION_LENGTH} characters.",
                "Description",
                "too_long",
            )
        )

    clean_tags = str(tags or "").strip().strip(",").strip()
    if len(clean_tags) > MAX_TAGS_LENGTH:
        errors.append(
            FieldError(
                "tags",
                f"Tags must be at most {MAX_TAGS_LENGTH} characters.",
                "Tags",
                "too_long",
            )
        )

    clean_url: Optional[str] = None
    if target_url is not None and str(target_url).strip():
        candidate = str(target_url).strip()
        if len(candidate) > MAX_TARGET_URL_LENGTH:
            errors.append(
                FieldError(
                    "target_url",
                    f"The page URL must be at most {MAX_TARGET_URL_LENGTH} characters.",
                    "Page URL",
                    "too_long",
                )
            )
        else:
            parsed = urlparse(candidate)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(
                    FieldError(
                        "target_url",
                        "The page URL must start with http:// or https://",
                        "Page URL",
                        "invalid_url",
                    )
                )
            else:
                clean_url = candidate

    if category not in BASE_CATEGORIES:
        errors.append(
            FieldError(
                "category",
                f"Unknown category '{category}'. Expected one of: {', '.join(BASE_CATEGORIES)}.",
                "Category",
                "not_an_option",
            )
        )
    if priority not in BASE_PRIORITIES:
        errors.append(
            FieldError(
                "priority",
                f"Unknown priority '{priority}'. Expected one of: {', '.join(BASE_PRIORITIES)}.",
                "Priority",
                "not_an_option",
            )
        )

    cleaned = {
        "title": clean_title,
        "description": clean_description,
        "tags": clean_tags,
        "target_url": clean_url,
        "category": category,
        "priority": priority,
    }
    return cleaned, errors


# --- Schema linting (admin side) ---------------------------------------------

def validate_field_schema(schema: Sequence[CustomFieldDefinition]) -> List[FieldError]:
    """Check an administrator's field schema before it is stored.

    Errors address ``fields_schema.<index>`` so the builder UI can point at the
    exact card that needs fixing.
    """
    problems: List[FieldError] = []
    if len(schema) > MAX_CUSTOM_FIELDS:
        return [
            FieldError(
                "fields_schema",
                f"A ticket type can define at most {MAX_CUSTOM_FIELDS} fields.",
                "Custom fields",
                "too_many_fields",
            )
        ]

    seen: Dict[str, int] = {}
    for index, field in enumerate(schema):
        address = f"fields_schema.{index}"
        if field.key in seen:
            problems.append(
                FieldError(
                    address,
                    f"Duplicate field key '{field.key}' (also used by field #{seen[field.key] + 1}).",
                    field.label,
                    "duplicate_key",
                )
            )
        else:
            seen[field.key] = index

    for index, field in enumerate(schema):
        address = f"fields_schema.{index}"
        for attribute, group in (("visible_when", field.visible_when), ("required_when", field.required_when)):
            if group is None:
                continue
            for condition in group.conditions:
                target = condition.field
                if target == field.key:
                    problems.append(
                        FieldError(
                            address,
                            f"'{field.label}' cannot depend on itself ({attribute}).",
                            field.label,
                            "self_reference",
                        )
                    )
                    continue
                if target not in seen:
                    problems.append(
                        FieldError(
                            address,
                            f"'{field.label}' depends on an unknown field '{target}' ({attribute}).",
                            field.label,
                            "unknown_reference",
                        )
                    )
                    continue
                if seen[target] >= index:
                    problems.append(
                        FieldError(
                            address,
                            f"'{field.label}' can only depend on fields defined above it "
                            f"('{target}' comes later).",
                            field.label,
                            "forward_reference",
                        )
                    )
    return problems
