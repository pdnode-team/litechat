"""Schemas for admin-defined ticket types and their dynamic form fields.

A field definition is a contract between three places that must agree:

1. the admin builder UI in the web client (what an administrator configures),
2. the customer-facing ticket form (what is rendered and pre-validated),
3. ``app.services.form_logic`` (the authoritative server-side validation).

Adding an attribute here without teaching the other two about it makes the form
drift, so treat this file as the single source of truth for the shape.

The whole schema is persisted as a JSON array in ``ticket_types.fields_schema_json``
(text column), so extending it needs no migration: older rows simply lack the new
keys and fall back to the defaults below.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Supported control types.
#   text / textarea / url / date / number / switch  -> scalar controls
#   select                                          -> single choice (optional "Other")
#   multi_select                                    -> zero or more choices (optional "Other")
FieldType = Literal[
    "text",
    "textarea",
    "select",
    "multi_select",
    "number",
    "switch",
    "url",
    "date",
]

FIELD_TYPES: tuple[str, ...] = (
    "text",
    "textarea",
    "select",
    "multi_select",
    "number",
    "switch",
    "url",
    "date",
)

# Condition operators used by `visible_when` / `required_when`.
ConditionOperator = Literal[
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "in",
    "not_in",
    "is_answered",
    "is_empty",
    "gt",
    "gte",
    "lt",
    "lte",
]

CONDITION_OPERATORS: tuple[str, ...] = (
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "in",
    "not_in",
    "is_answered",
    "is_empty",
    "gt",
    "gte",
    "lt",
    "lte",
)

# Operators that ignore `value` (they only look at whether the field was filled).
UNARY_OPERATORS = frozenset({"is_answered", "is_empty"})

LogicMode = Literal["all", "any"]

# Deliberately permissive: legacy rows were written before this schema existed
# and may contain capital letters, dashes or a leading digit. The admin builder
# normalises new keys to snake_case.
FIELD_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$"

MAX_FIELDS_PER_TYPE = 50
MAX_OPTIONS = 100
MAX_OPTION_LENGTH = 120
MAX_TEXT_LENGTH = 20000


def _coerce_str_list(value: Any) -> List[str]:
    """Accept a list, a comma separated string or None and return clean strings."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        text = text[:MAX_OPTION_LENGTH]
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= MAX_OPTIONS:
            break
    return cleaned


class FieldCondition(BaseModel):
    """A single test against the answer of another field of the same form."""

    field: str = Field(min_length=1, max_length=40)
    operator: ConditionOperator = "equals"
    value: Any = None


class ConditionGroup(BaseModel):
    """One or more conditions combined with all/any semantics.

    A bare condition object is accepted as shorthand for a single-condition
    "all" group, so hand-written JSON stays readable.
    """

    logic: LogicMode = "all"
    conditions: List[FieldCondition] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, data: Any) -> Any:
        if isinstance(data, dict) and "conditions" not in data and "field" in data:
            return {"logic": "all", "conditions": [data]}
        if isinstance(data, dict) and isinstance(data.get("conditions"), dict):
            return {**data, "conditions": [data["conditions"]]}
        return data


class CustomFieldDefinition(BaseModel):
    """One question of a dynamic ticket form."""

    key: str = Field(min_length=1, max_length=40, pattern=FIELD_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    type: FieldType = "text"
    required: bool = False
    placeholder: str = Field(default="", max_length=120)
    help_text: str = Field(default="", max_length=300)

    # select / multi_select
    options: List[str] = Field(default_factory=list)
    allow_other: bool = False
    other_label: str = Field(default="Other", max_length=60)

    # Length / value constraints. `error_message` replaces the generated wording
    # for the length, pattern and range checks (not for "required").
    min_length: Optional[int] = Field(default=None, ge=0, le=MAX_TEXT_LENGTH)
    max_length: Optional[int] = Field(default=None, ge=1, le=MAX_TEXT_LENGTH)
    pattern: Optional[str] = Field(default=None, max_length=300)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    error_message: Optional[str] = Field(default=None, max_length=300)

    # Conditional logic. Conditions may only reference fields defined *above*
    # this one, which is what keeps evaluation order well defined.
    visible_when: Optional[ConditionGroup] = None
    required_when: Optional[ConditionGroup] = None

    # Ignore unknown keys so a schema written by a newer client still loads.
    model_config = ConfigDict(extra="ignore")

    @field_validator("options", mode="before")
    @classmethod
    def _validate_options(cls, value: Any) -> List[str]:
        return _coerce_str_list(value)

    @field_validator("placeholder", "help_text", "other_label", mode="before")
    @classmethod
    def _blank_instead_of_none(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("error_message", "pattern", mode="before")
    @classmethod
    def _none_instead_of_blank(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("label", mode="before")
    @classmethod
    def _label_instead_of_none(cls, value: Any) -> Any:
        return "" if value is None else value

    @model_validator(mode="after")
    def _check_consistency(self) -> "CustomFieldDefinition":
        if self.type in ("select", "multi_select") and not self.options and not self.allow_other:
            raise ValueError(
                f"Field '{self.key}' is a {self.type} and needs at least one option (or 'allow other')."
            )
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError(f"Field '{self.key}': min_length cannot be greater than max_length.")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f"Field '{self.key}': min_value cannot be greater than max_value.")
        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as exc:  # pragma: no cover - message is asserted in tests
                raise ValueError(f"Field '{self.key}': invalid regular expression ({exc}).") from exc
        return self


class TicketTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    description: Optional[str] = Field(default="", max_length=255)
    fields_schema: List[CustomFieldDefinition] = Field(default_factory=list)
    is_active: bool = True


class TicketTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)
    fields_schema: Optional[List[CustomFieldDefinition]] = None
    is_active: Optional[bool] = None


class TicketTypeResponse(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str] = ""
    fields_schema: List[CustomFieldDefinition] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def field_to_dict(field: CustomFieldDefinition) -> Dict[str, Any]:
    """Compact storage form: only non-default keys are persisted."""
    return field.model_dump(exclude_defaults=True, exclude_none=True)


def schema_to_json(fields: List[CustomFieldDefinition]) -> str:
    import json

    return json.dumps([field_to_dict(f) for f in fields])


def repair_legacy_field(raw: Any, index: int) -> Optional[CustomFieldDefinition]:
    """Best-effort load of a field definition written by an older version.

    Rows created before this schema existed may be missing a label, carry an
    unknown control type, or store options as a comma separated string. Repair
    what can be repaired instead of silently dropping the question - a form that
    quietly loses a field is worse than one that shows a slightly odd one.

    Returns ``None`` only when the entry is not usable at all (not a mapping).
    """
    if not isinstance(raw, dict):
        return None

    data: Dict[str, Any] = dict(raw)
    key = str(data.get("key") or f"field_{index + 1}").strip()
    data["key"] = key
    if not str(data.get("label") or "").strip():
        data["label"] = key.replace("_", " ").title() or f"Field {index + 1}"
    if data.get("type") not in FIELD_TYPES:
        data["type"] = "text"
    data.pop("id", None)
    # `options: null` used to be written by the admin builder.
    data["options"] = _coerce_str_list(data.get("options"))

    try:
        return CustomFieldDefinition(**data)
    except Exception:
        return None
