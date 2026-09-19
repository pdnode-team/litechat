"""Outbound email.

Delivery settings come from the runtime settings store (editable in the admin
UI) with environment variables as the fallback. When no SMTP host is
configured, messages are logged instead of sent, so password-reset and
verification links stay usable in development without a mail server.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import List, Optional

from app.services import settings_service

logger = logging.getLogger("litechat.email")


def _build_message(smtp_from: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def _send_sync(config: dict, message: EmailMessage) -> None:
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"], timeout=15) as smtp:
        if config["smtp_use_tls"]:
            smtp.starttls()
        if config["smtp_username"] and config["smtp_password"]:
            smtp.login(config["smtp_username"], config["smtp_password"])
        smtp.send_message(message)


async def send_email(to: str, subject: str, body: str) -> bool:
    """Deliver an email. Returns True when it was handed to SMTP.

    Delivery failures are logged rather than raised: the endpoints that trigger
    mail must not leak whether an address exists, and must not fail because the
    mail server is briefly unavailable.
    """
    if not to:
        return False

    config = await settings_service.get_all()
    if not config.get("smtp_enabled") or not config.get("smtp_host"):
        logger.warning(
            "SMTP not configured - email to %s was not sent. Subject: %s\n%s",
            to,
            subject,
            body,
        )
        return False

    message = _build_message(config["smtp_from"], to, subject, body)

    try:
        await asyncio.to_thread(_send_sync, config, message)
        logger.info("Email sent to %s (%s)", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


async def send_test_email(to: str) -> tuple[bool, str]:
    """Send a verification message; unlike send_email this reports why it failed."""
    config = await settings_service.get_all()
    if not config.get("smtp_enabled"):
        return False, "Outbound email is disabled."
    if not config.get("smtp_host"):
        return False, "No SMTP host is configured."

    message = _build_message(
        config["smtp_from"],
        to,
        "LiteChat SMTP test",
        (
            "This is a test message from LiteChat.\n\n"
            "If you received it, your SMTP settings are working.\n"
            f"Host: {config['smtp_host']}:{config['smtp_port']}  STARTTLS: {config['smtp_use_tls']}"
        ),
    )

    try:
        await asyncio.to_thread(_send_sync, config, message)
    except Exception as exc:
        logger.exception("SMTP test to %s failed", to)
        return False, f"{type(exc).__name__}: {exc}"

    return True, f"Test message sent to {to}."


async def _app_url() -> str:
    return (await settings_service.get("public_app_url") or "").rstrip("/")


async def send_password_reset_email(to: str, raw_token: str) -> None:
    link = f"{await _app_url()}/?reset_token={raw_token}"
    await send_email(
        to,
        "Reset your LiteChat password",
        (
            "A password reset was requested for your LiteChat account.\n\n"
            f"Open this link to choose a new password:\n{link}\n\n"
            "If you did not request this, you can safely ignore this email. "
            "The link expires shortly and can only be used once."
        ),
    )


async def send_email_verification_email(to: str, raw_token: str) -> None:
    link = f"{await _app_url()}/?verify_token={raw_token}"
    await send_email(
        to,
        "Confirm your LiteChat email address",
        (
            "Welcome to LiteChat.\n\n"
            f"Confirm your email address by opening this link:\n{link}\n\n"
            "If you did not create this account, you can ignore this email."
        ),
    )


async def send_ticket_notification(
    recipients: List[str],
    subject: str,
    heading: str,
    lines: List[str],
    ticket_id: int,
    action_label: Optional[str] = None,
) -> None:
    """Send a ticket-related notification to every recipient."""
    if not recipients:
        return

    url = f"{await _app_url()}/?ticket={ticket_id}"
    body = "\n".join(
        [
            heading,
            "",
            *lines,
            "",
            f"{action_label or 'Open the ticket'}: {url}",
            "",
            "You are receiving this because email notifications are enabled for this workspace.",
        ]
    )

    for recipient in recipients:
        await send_email(recipient, subject, body)
