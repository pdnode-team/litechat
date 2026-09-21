"""Escape user input before it is used in a SQL LIKE / ILIKE pattern."""


def like_contains(term: str) -> str:
    """Wrap ``term`` in wildcards after escaping ``\\``, ``%`` and ``_``."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


LIKE_ESCAPE = "\\"
