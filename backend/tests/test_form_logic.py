"""Unit tests for the dynamic-form rules.

These are the authoritative definitions of what a ticket submission may contain;
the browser mirrors them, so they are tested directly rather than only through
the HTTP layer.
"""
from app.schemas.ticket_type import (
    ConditionGroup,
    CustomFieldDefinition,
    FieldCondition,
    repair_legacy_field,
)
from app.services.form_logic import (
    evaluate_form,
    is_field_required,
    is_field_visible,
    validate_base_fields,
    validate_custom_fields,
    validate_field_schema,
)


def field(**kwargs) -> CustomFieldDefinition:
    kwargs.setdefault("key", "k")
    kwargs.setdefault("label", "Label")
    return CustomFieldDefinition(**kwargs)


def codes(errors) -> dict:
    return {error.field: error.code for error in errors}


# --- Conditions --------------------------------------------------------------

def test_condition_equals_is_case_insensitive_and_type_tolerant():
    target = field(
        visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="High")])
    )
    assert is_field_visible(target, {"severity": " high "})
    assert is_field_visible(target, {"severity": "HIGH"})
    assert not is_field_visible(target, {"severity": "Low"})
    assert not is_field_visible(target, {})


def test_condition_equals_on_a_multi_select_answer():
    condition = FieldCondition(field="browsers", operator="equals", value="Chrome")
    target = field(visible_when=ConditionGroup(conditions=[condition]))
    assert is_field_visible(target, {"browsers": ["Firefox", "Chrome"]})
    assert not is_field_visible(target, {"browsers": ["Firefox"]})


def test_boolean_and_numeric_conditions_compare_by_value():
    truthy = field(visible_when=ConditionGroup(conditions=[FieldCondition(field="flag", operator="equals", value=True)]))
    assert is_field_visible(truthy, {"flag": "true"})
    assert is_field_visible(truthy, {"flag": 1})

    numeric = field(visible_when=ConditionGroup(conditions=[FieldCondition(field="count", operator="gt", value=3)]))
    assert is_field_visible(numeric, {"count": "10"})
    assert not is_field_visible(numeric, {"count": 3})
    assert not is_field_visible(numeric, {"count": "many"})


def test_unary_and_membership_operators():
    answered = field(visible_when=ConditionGroup(conditions=[FieldCondition(field="a", operator="is_answered")]))
    assert is_field_visible(answered, {"a": "x"})
    assert not is_field_visible(answered, {"a": "   "})
    assert not is_field_visible(answered, {"a": []})

    empty = field(visible_when=ConditionGroup(conditions=[FieldCondition(field="a", operator="is_empty")]))
    assert is_field_visible(empty, {})
    assert not is_field_visible(empty, {"a": "x"})

    contained = field(
        visible_when=ConditionGroup(conditions=[FieldCondition(field="plan", operator="in", value=["pro", "team"])])
    )
    assert is_field_visible(contained, {"plan": "PRO"})
    assert not is_field_visible(contained, {"plan": "free"})

    text = field(
        visible_when=ConditionGroup(conditions=[FieldCondition(field="msg", operator="contains", value="timeout")])
    )
    assert is_field_visible(text, {"msg": "Request TIMEOUT after 30s"})
    assert not is_field_visible(text, {"msg": "all good"})


def test_condition_group_logic_all_and_any():
    first = FieldCondition(field="a", operator="equals", value="1")
    second = FieldCondition(field="b", operator="equals", value="2")

    both = field(visible_when=ConditionGroup(logic="all", conditions=[first, second]))
    assert is_field_visible(both, {"a": "1", "b": "2"})
    assert not is_field_visible(both, {"a": "1"})

    either = field(visible_when=ConditionGroup(logic="any", conditions=[first, second]))
    assert is_field_visible(either, {"a": "1"})
    assert not is_field_visible(either, {"c": "3"})


def test_a_bare_condition_dict_is_accepted_as_shorthand():
    parsed = CustomFieldDefinition(
        key="x",
        label="X",
        visible_when={"field": "severity", "operator": "equals", "value": "High"},
    )
    assert parsed.visible_when is not None
    assert len(parsed.visible_when.conditions) == 1
    assert parsed.visible_when.logic == "all"


# --- Visibility --------------------------------------------------------------

def test_hiding_a_field_hides_whatever_depended_on_it():
    schema = [
        field(key="severity", label="Severity", type="select", options=["Low", "High"]),
        field(
            key="crash_id",
            label="Crash id",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="High")]),
        ),
        field(
            key="trace",
            label="Trace",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="crash_id", operator="is_answered")]),
        ),
    ]

    low = evaluate_form(schema, {"severity": "Low", "crash_id": "abc", "trace": "boom"})
    assert low.visible_keys == ["severity"]
    assert low.hidden_keys == ["crash_id", "trace"]

    high = evaluate_form(schema, {"severity": "High", "crash_id": "abc", "trace": "boom"})
    assert high.visible_keys == ["severity", "crash_id", "trace"]


def test_answers_to_hidden_fields_are_dropped_not_stored():
    schema = [
        field(key="severity", label="Severity", type="select", options=["Low", "High"]),
        field(
            key="downtime",
            label="Downtime",
            type="number",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="High")]),
        ),
    ]
    cleaned, errors = validate_custom_fields(schema, {"severity": "Low", "downtime": 90})
    assert errors == []
    assert cleaned == {"severity": "Low"}


def test_required_when_only_applies_while_the_condition_holds():
    conditional = field(
        key="crash_id",
        label="Crash id",
        required_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="High")]),
    )
    assert is_field_required(conditional, {"severity": "High"})
    assert not is_field_required(conditional, {"severity": "Low"})


# --- Field validation --------------------------------------------------------

def test_required_hidden_field_is_not_required():
    schema = [
        field(key="severity", label="Severity", type="select", options=["Low", "High"]),
        field(
            key="crash_id",
            label="Crash id",
            required=True,
            visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="High")]),
        ),
    ]
    cleaned, errors = validate_custom_fields(schema, {"severity": "Low"})
    assert errors == []
    assert cleaned == {"severity": "Low"}

    _, errors = validate_custom_fields(schema, {"severity": "High"})
    assert codes(errors) == {"custom_fields.crash_id": "required"}


def test_text_constraints_use_the_administrators_own_message():
    schema = [
        field(
            key="order",
            label="Order number",
            min_length=6,
            max_length=8,
            error_message="Order numbers are 6 to 8 characters.",
        )
    ]
    _, errors = validate_custom_fields(schema, {"order": "123"})
    assert errors[0].message == "Order numbers are 6 to 8 characters."

    cleaned, errors = validate_custom_fields(schema, {"order": " 123456 "})
    assert errors == []
    assert cleaned == {"order": "123456"}


def test_pattern_must_match_the_whole_value():
    schema = [field(key="zip", label="ZIP", pattern=r"\d{5}")]
    assert validate_custom_fields(schema, {"zip": "12345"})[1] == []
    assert codes(validate_custom_fields(schema, {"zip": "abc12345"})[1]) == {"custom_fields.zip": "pattern_mismatch"}


def test_numbers_are_range_checked_and_normalised():
    schema = [field(key="count", label="Seats", type="number", min_value=1, max_value=50)]
    cleaned, errors = validate_custom_fields(schema, {"count": "12"})
    assert errors == []
    assert cleaned == {"count": 12}

    assert codes(validate_custom_fields(schema, {"count": 0})[1]) == {"custom_fields.count": "too_small"}
    assert codes(validate_custom_fields(schema, {"count": 51})[1]) == {"custom_fields.count": "too_large"}
    assert codes(validate_custom_fields(schema, {"count": "abc"})[1]) == {"custom_fields.count": "not_a_number"}


def test_url_and_date_fields_are_format_checked():
    schema = [field(key="page", label="Page", type="url"), field(key="when", label="When", type="date")]
    assert validate_custom_fields(schema, {"page": "https://a.test/x", "when": "2026-01-31"})[1] == []
    assert codes(validate_custom_fields(schema, {"page": "a.test/x"})[1]) == {"custom_fields.page": "invalid_url"}
    assert codes(validate_custom_fields(schema, {"when": "31/01/2026"})[1]) == {"custom_fields.when": "invalid_date"}


def test_switches_accept_common_truthy_spellings():
    schema = [field(key="ok", label="OK", type="switch")]
    assert validate_custom_fields(schema, {"ok": "on"})[0] == {"ok": True}
    assert validate_custom_fields(schema, {"ok": False})[0] == {"ok": False}
    assert codes(validate_custom_fields(schema, {"ok": "maybe"})[1]) == {"custom_fields.ok": "invalid"}


def test_select_rejects_values_outside_the_option_list():
    schema = [field(key="severity", label="Severity", type="select", options=["Low", "High"])]
    assert codes(validate_custom_fields(schema, {"severity": "Critical"})[1]) == {
        "custom_fields.severity": "not_an_option"
    }
    assert validate_custom_fields(schema, {"severity": "High"})[0] == {"severity": "High"}


def test_select_with_allow_other_accepts_free_text():
    schema = [field(key="severity", label="Severity", type="select", options=["Low", "High"], allow_other=True)]
    cleaned, errors = validate_custom_fields(schema, {"severity": "Everything is on fire"})
    assert errors == []
    assert cleaned == {"severity": "Everything is on fire"}


def test_multi_select_normalises_deduplicates_and_validates():
    schema = [field(key="browsers", label="Browsers", type="multi_select", options=["Chrome", "Firefox"])]
    cleaned, errors = validate_custom_fields(schema, {"browsers": ["Firefox", "Chrome", "Firefox"]})
    assert errors == []
    assert cleaned == {"browsers": ["Firefox", "Chrome"]}

    assert codes(validate_custom_fields(schema, {"browsers": ["Edge"]})[1]) == {
        "custom_fields.browsers": "not_an_option"
    }


def test_multi_select_with_other_allows_one_custom_answer():
    schema = [field(key="browsers", label="Browsers", type="multi_select", options=["Chrome"], allow_other=True)]
    cleaned, errors = validate_custom_fields(schema, {"browsers": ["Chrome", "Lynx"]})
    assert errors == []
    assert cleaned == {"browsers": ["Chrome", "Lynx"]}

    _, errors = validate_custom_fields(schema, {"browsers": ["Lynx", "W3M"]})
    assert codes(errors) == {"custom_fields.browsers": "too_many_custom_answers"}


def test_unknown_and_unexpected_fields_are_rejected():
    schema = [field(key="severity", label="Severity", type="text")]
    _, errors = validate_custom_fields(schema, {"severity": "x", "mystery": "y"})
    assert codes(errors) == {"custom_fields.mystery": "unknown_field"}

    _, errors = validate_custom_fields([], {"severity": "x"})
    assert codes(errors) == {"custom_fields": "unexpected_fields"}


def test_errors_are_reported_for_every_problem_at_once():
    schema = [
        field(key="severity", label="Severity", type="select", required=True, options=["Low", "High"]),
        field(key="seats", label="Seats", type="number", min_value=1),
    ]
    _, errors = validate_custom_fields(schema, {"severity": "Nope", "seats": 0})
    assert set(codes(errors)) == {"custom_fields.severity", "custom_fields.seats"}


# --- Built-in fields ---------------------------------------------------------

def test_base_field_validation_reports_every_problem():
    cleaned, errors = validate_base_fields(
        title="ab",
        description="hi",
        tags="x" * 501,
        target_url="example.com/nope",
        category="nonsense",
        priority="urgent",
    )
    assert set(codes(errors)) == {"title", "description", "tags", "target_url", "category"}
    assert cleaned["priority"] == "urgent"


def test_base_field_validation_cleans_and_accepts_valid_input():
    cleaned, errors = validate_base_fields(
        title="  Printer on fire  ",
        description="  Smoke is coming out of the back.  ",
        tags=" hardware, urgent ,, ",
        target_url="  https://status.test/x  ",
    )
    assert errors == []
    assert cleaned == {
        "title": "Printer on fire",
        "description": "Smoke is coming out of the back.",
        "tags": "hardware, urgent",
        "target_url": "https://status.test/x",
        "category": "general",
        "priority": "medium",
    }


# --- Schema linting ----------------------------------------------------------

def test_schema_linting_catches_duplicates_and_bad_references():
    schema = [
        field(key="severity", label="Severity", type="select", options=["Low"]),
        field(key="severity", label="Severity again"),
        field(
            key="crash",
            label="Crash",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="Low")]),
        ),
        field(
            key="trace",
            label="Trace",
            required_when=ConditionGroup(conditions=[FieldCondition(field="crash", operator="is_answered")]),
        ),
        field(
            key="loop",
            label="Loop",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="loop", operator="is_answered")]),
        ),
        field(
            key="ghost",
            label="Ghost",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="nobody", operator="is_answered")]),
        ),
    ]
    problems = validate_field_schema(schema)
    reported = {problem.field: problem.code for problem in problems}
    assert reported["fields_schema.1"] == "duplicate_key"
    # `trace` references `crash`, which is defined above it: that is allowed.
    assert "fields_schema.3" not in reported
    assert reported["fields_schema.4"] == "self_reference"
    assert reported["fields_schema.5"] == "unknown_reference"


def test_schema_linting_rejects_a_forward_reference():
    schema = [
        field(
            key="early",
            label="Early",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="late", operator="is_answered")]),
        ),
        field(key="late", label="Late"),
    ]
    problems = validate_field_schema(schema)
    assert [p.code for p in problems] == ["forward_reference"]


def test_schema_linting_accepts_a_valid_schema():
    schema = [
        field(key="severity", label="Severity", type="select", options=["Low"]),
        field(
            key="crash",
            label="Crash",
            visible_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="Low")]),
            required_when=ConditionGroup(conditions=[FieldCondition(field="severity", operator="equals", value="Low")]),
        ),
    ]
    assert validate_field_schema(schema) == []


# --- Legacy schema repair ----------------------------------------------------

def test_legacy_fields_are_repaired_rather_than_dropped():
    repaired = repair_legacy_field({"key": "os", "type": "select", "options": "Windows, macOS"}, 0)
    assert repaired is not None
    assert repaired.label == "Os"  # label was missing; derived from the key
    assert repaired.options == ["Windows", "macOS"]

    repaired = repair_legacy_field({"key": "note", "label": "Note", "type": "banana", "options": None}, 1)
    assert repaired is not None
    assert repaired.type == "text"
    assert repaired.options == []

    assert repair_legacy_field("not a mapping", 2) is None
