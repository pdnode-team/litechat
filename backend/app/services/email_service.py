"""Outbound email.

With ``SMTP_HOST`` configured, mail is sent over SMTP. Without it — the default
in development — the message is logged instead, so password-reset and
verification links remain usable locally without a mail server.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import (
    PUBLIC_APP_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)

logger = logging.getLogger("litechat.email")


def _send_sync(message: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


async def send_email(to: str, subject: str, body: str) -> None:
    """Deliver an email, or log it when no SMTP host is configured.

    Delivery failures are logged rather than raised: the endpoints that trigger
    mail must not leak whether an address exists, and must not fail because the
    mail server is briefly unavailable.
    """
    if not SMTP_HOST:
        logger.warning(
            "SMTP not configured - email to %s was not sent. Subject: %s\n%s",
            to,
            subject,
            body,
        )
        return

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        # smtplib is blocking; keep it off the event loop.
        await asyncio.to_thread(_send_sync, message)
    except Exception:
        logger.exception("Failed to send email to %s", to)


async def send_password_reset_email(to: str, raw_token: str) -> None:
    link = f"{PUBLIC_APP_URL}/?reset_token={raw_token}"
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
    link = f"{PUBLIC_APP_URL}/?verify_token={raw_token}"
    await send_email(
        to,
        "Confirm your LiteChat email address",
        (
            "Welcome to LiteChat.\n\n"
            f"Confirm your email address by opening this link:\n{link}\n\n"
            "If you did not create this account, you can ignore this email."
        ),
    )
