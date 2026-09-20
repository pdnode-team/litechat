"""UTC storage conventions.

These guard a bug that is invisible on SQLite and fatal on PostgreSQL: asyncpg
encodes `timestamp without time zone` by subtracting a naive epoch, so binding
an aware datetime raises "can't subtract offset-naive and offset-aware
datetimes". SQLite stores the string and drops tzinfo, so the test suite stayed
green while `POST /api/tickets` returned 500 in production.
"""
from datetime import datetime, timedelta, timezone

import app.models  # noqa: F401  — populates Base.metadata for the structural check
from app.db.base import Base, UTCDateTime, utcnow


def test_utcdatetime_converts_aware_values_to_naive_utc():
    decorator = UTCDateTime()
    # 12:00 at UTC+8 is 04:00 UTC.
    aware = datetime(2026, 9, 19, 12, 0, tzinfo=timezone(timedelta(hours=8)))

    bound = decorator.process_bind_param(aware, None)

    assert bound.tzinfo is None
    assert bound == datetime(2026, 9, 19, 4, 0)


def test_utcdatetime_passes_naive_values_through_unchanged():
    decorator = UTCDateTime()
    naive = datetime(2026, 9, 19, 12, 0)

    assert decorator.process_bind_param(naive, None) == naive
    assert decorator.process_bind_param(None, None) is None


def test_utcdatetime_normalises_on_read_too():
    decorator = UTCDateTime()
    aware = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

    assert decorator.process_result_value(aware, None).tzinfo is None


def test_utcnow_returns_a_naive_datetime():
    assert utcnow().tzinfo is None


def test_every_datetime_column_uses_utcdatetime():
    """A plain DateTime column would reintroduce the production-only crash."""
    offenders = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            try:
                python_type = column.type.python_type
            except NotImplementedError:
                continue
            if python_type is not datetime:
                continue
            if not isinstance(column.type, UTCDateTime):
                offenders.append(f"{table.name}.{column.name} -> {type(column.type).__name__}")

    assert not offenders, (
        "DateTime columns must use UTCDateTime (naive UTC), otherwise binding an "
        f"aware datetime fails on PostgreSQL: {offenders}"
    )
