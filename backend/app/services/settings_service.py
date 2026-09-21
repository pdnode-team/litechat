"""Runtime settings: database values with environment-variable fallbacks.

Resolution order for every key is:

1. a row in ``app_settings`` (editable from the admin UI)
2. the corresponding environment variable
3. the built-in default

The settings table is small and read on every notification decision, so the
resolved values are cached in-process and invalidated whenever the API writes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import select

from app import config as app_config
from app.config import SLA_FIRST_RESPONSE_MINUTES, SLA_RESOLUTION_MINUTES
from app.db.session import async_session_factory
from app.models.app_setting import AppSetting
from app.services import secret_box

logger = logging.getLogger("litechat.settings")


@dataclass(frozen=True)
class SettingSpec:
    key: str
    env_var: Optional[str]
    default: Any
    kind: str  # "str" | "int" | "bool"
    is_secret: bool = False
    label: str = ""


SPECS: tuple[SettingSpec, ...] = (
    # ── Email delivery ────────────────────────────────────────────────
    SettingSpec("smtp_enabled", None, None, "bool", label="Enable outbound email"),
    SettingSpec("smtp_host", "SMTP_HOST", "", "str", label="SMTP host"),
    SettingSpec("smtp_port", "SMTP_PORT", 587, "int", label="SMTP port"),
    SettingSpec("smtp_username", "SMTP_USERNAME", "", "str", label="SMTP username"),
    SettingSpec("smtp_password", "SMTP_PASSWORD", "", "str", True, "SMTP password"),
    SettingSpec("smtp_use_tls", "SMTP_USE_TLS", True, "bool", label="Use STARTTLS"),
    SettingSpec("smtp_from", "SMTP_FROM", "no-reply@litechat.local", "str", label="From address"),
    SettingSpec("public_app_url", "PUBLIC_APP_URL", "http://localhost:3000", "str", label="App base URL"),
    # ── Notification policy ───────────────────────────────────────────
    SettingSpec("notify_new_ticket", None, True, "bool", label="Email staff on new tickets"),
    SettingSpec("notify_ticket_reply", None, True, "bool", label="Email on new replies"),
    SettingSpec("notify_assignment", None, True, "bool", label="Email the assignee"),
    SettingSpec("notify_status_change", None, True, "bool", label="Email the customer on resolve/close"),
    SettingSpec("support_email", None, "", "str", label="Support inbox (optional extra recipient)"),
    # ── SLA ───────────────────────────────────────────────────────────
    SettingSpec("sla_first_urgent", None, SLA_FIRST_RESPONSE_MINUTES["urgent"], "int", label="Urgent first response (min)"),
    SettingSpec("sla_first_high", None, SLA_FIRST_RESPONSE_MINUTES["high"], "int", label="High first response (min)"),
    SettingSpec("sla_first_medium", None, SLA_FIRST_RESPONSE_MINUTES["medium"], "int", label="Medium first response (min)"),
    SettingSpec("sla_first_low", None, SLA_FIRST_RESPONSE_MINUTES["low"], "int", label="Low first response (min)"),
    SettingSpec("sla_resolution_urgent", None, SLA_RESOLUTION_MINUTES["urgent"], "int", label="Urgent resolution (min)"),
    SettingSpec("sla_resolution_high", None, SLA_RESOLUTION_MINUTES["high"], "int", label="High resolution (min)"),
    SettingSpec("sla_resolution_medium", None, SLA_RESOLUTION_MINUTES["medium"], "int", label="Medium resolution (min)"),
    SettingSpec("sla_resolution_low", None, SLA_RESOLUTION_MINUTES["low"], "int", label="Low resolution (min)"),
    SettingSpec("sla_business_hours_enabled", None, False, "bool", label="Count only business hours"),
    SettingSpec("sla_weekdays", None, "mon,tue,wed,thu,fri", "str", label="Business days"),
    SettingSpec("sla_start", None, "09:00", "str", label="Business day start"),
    SettingSpec("sla_end", None, "18:00", "str", label="Business day end"),
    SettingSpec("sla_timezone", None, "UTC", "str", label="Business timezone"),
    SettingSpec("sla_observe_holidays", None, False, "bool", label="Skip holidays (not implemented)"),
)

SPEC_BY_KEY = {spec.key: spec for spec in SPECS}

_cache: Optional[Dict[str, Any]] = None


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    if raw is None:
        return None
    if spec.kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if spec.kind == "int":
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return spec.default
    return str(raw)


def _env_value(spec: SettingSpec) -> Any:
    if spec.env_var is None:
        return None
    raw = getattr(app_config, spec.env_var, None)
    return raw


def _default_for(spec: SettingSpec) -> Any:
    # smtp_enabled is derived: enabled automatically when a host is configured.
    if spec.key == "smtp_enabled":
        return None
    return spec.default


def resolve(stored: Dict[str, str], spec: SettingSpec) -> Any:
    """Resolve one setting from DB -> env -> default."""
    if spec.key in stored:
        raw = secret_box.decrypt(stored[spec.key]) if spec.is_secret else stored[spec.key]
        return _coerce(spec, raw)

    env = _env_value(spec)
    if env not in (None, ""):
        return _coerce(spec, env)

    if spec.key == "smtp_enabled":
        # "enabled" unless a host is configured or explicitly turned off.
        return None

    return _default_for(spec)


async def _load_stored() -> Dict[str, str]:
    try:
        async with async_session_factory() as session:
            rows = (await session.execute(select(AppSetting))).scalars().all()
            return {row.key: (row.value or "") for row in rows}
    except Exception as exc:  # table missing before migration, etc.
        logger.warning("Could not read app_settings (%s); using environment only", exc)
        return {}


async def get_all(force: bool = False) -> Dict[str, Any]:
    """Every resolved setting. Secrets are included and must be filtered by callers."""
    global _cache
    if _cache is not None and not force:
        return _cache

    stored = await _load_stored()
    values: Dict[str, Any] = {}
    for spec in SPECS:
        values[spec.key] = resolve(stored, spec)

    # Explicit DB/env value wins; otherwise fall back to "is a host configured?".
    if values.get("smtp_enabled") is None:
        values["smtp_enabled"] = bool(values.get("smtp_host"))

    _cache = values
    return values


async def get(key: str) -> Any:
    return (await get_all()).get(key)


async def set_many(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Persist settings. ``None`` values are left untouched; ``""`` clears a key."""
    unknown = set(updates) - set(SPEC_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown setting(s): {sorted(unknown)}")

    async with async_session_factory() as session:
        for key, value in updates.items():
            if value is None:
                continue
            spec = SPEC_BY_KEY[key]
            if isinstance(value, bool):
                raw = "true" if value else "false"
            else:
                raw = str(value)

            stored = "" if raw == "" else (secret_box.encrypt(raw) if spec.is_secret else raw)

            row = await session.get(AppSetting, key)
            if row is None:
                session.add(AppSetting(key=key, value=stored, is_secret=spec.is_secret))
            else:
                row.value = stored
                row.is_secret = spec.is_secret
        await session.commit()

    invalidate()
    return await get_all(force=True)


def invalidate() -> None:
    global _cache
    _cache = None


def public_view(values: Dict[str, Any]) -> Dict[str, Any]:
    """Settings safe to return over the API: secrets become a set/unset marker."""
    result: Dict[str, Any] = {}
    for spec in SPECS:
        value = values.get(spec.key)
        if spec.is_secret:
            result[f"{spec.key}_set"] = bool(value)
        else:
            result[spec.key] = value
    return result
