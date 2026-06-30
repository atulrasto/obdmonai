"""Async email helpers — used for welcome emails and future notifications."""
from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

log = logging.getLogger(__name__)


async def _send(msg: EmailMessage) -> None:
    """Low-level send via aiosmtplib; skipped silently when SMTP is not configured."""
    if not settings.smtp_host or not settings.smtp_user:
        log.warning("SMTP not configured — skipping email to %s", msg["To"])
        return

    try:
        if settings.smtp_tls:
            # Port 465: SSL from connection start
            async with aiosmtplib.SMTP(
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                use_tls=True,
            ) as smtp:
                await smtp.login(settings.smtp_user, settings.smtp_password)
                await smtp.send_message(msg)
        else:
            # Port 587: plain connect then STARTTLS
            async with aiosmtplib.SMTP(
                hostname=settings.smtp_host,
                port=settings.smtp_port,
            ) as smtp:
                await smtp.starttls()
                await smtp.login(settings.smtp_user, settings.smtp_password)
                await smtp.send_message(msg)

        log.info("Email sent to %s subject=%r", msg["To"], msg["Subject"])
    except Exception as exc:
        log.error("Failed to send email to %s: %s", msg["To"], exc)


async def send_welcome_email(
    to_email: str,
    client_name: str,
    temp_password: str,
) -> None:
    """Send new-client welcome email with temp credentials."""
    domain = settings.cell_domain
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = f"Welcome to obdmonai — Your Fleet Account is Ready"
    msg.set_content(f"""\
Welcome to obdmonai, {client_name}!

Your fleet management account has been created.

Login URL : https://{domain}/login
Email     : {to_email}
Password  : {temp_password}

You will be asked to change this password on your first login.

If you have any questions, reply to this email.

— The obdmonai team
""")
    await _send(msg)


async def send_alert_email(subject: str, body: str) -> None:
    """Send a Tier A alert to the configured smtp_to address(es)."""
    if not settings.smtp_to:
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg["Subject"] = subject
    msg.set_content(body)
    await _send(msg)
