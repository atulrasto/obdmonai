"""Tier A — notification dispatch.

Logs every alert transition, optionally sends an SMTP email and/or POSTs to
a webhook.  Delivery dedupe is inherent: this is only called when the rules
engine produces a 'fire' or 'clear' action, which requires a state transition
in the database.  Duplicate telemetry readings produce action='none' and never
reach this function.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings
from app.tier_a.rules import RuleResult, TelemetryReading

log = logging.getLogger(__name__)


def dispatch_notification(result: RuleResult, reading: TelemetryReading) -> None:
    """Fire-and-forget notification for an alert transition.

    Runs the async work in a background task on the running event loop so the
    caller (engine) is not blocked.
    """
    log.info(
        "ALERT [%s] rule=%s device=%s detail=%s",
        result.action.upper(),
        result.rule,
        reading.device_id,
        result.detail,
    )
    loop = asyncio.get_event_loop()
    loop.create_task(_dispatch_async(result, reading))


async def _dispatch_async(result: RuleResult, reading: TelemetryReading) -> None:
    subject = f"[obdmonai] {result.action.upper()} — {result.rule} (device {reading.device_id})"
    body = (
        f"Rule:    {result.rule}\n"
        f"Action:  {result.action}\n"
        f"Severity:{result.severity}\n"
        f"Device:  {reading.device_id}\n"
        f"Vehicle: {reading.vehicle_id}\n"
        f"Client:  {reading.client_id}\n"
        f"At:      {reading.ts.isoformat()}\n"
        f"Detail:  {result.detail}\n"
    )

    tasks = []
    if settings.smtp_host and settings.smtp_to:
        tasks.append(_send_email(subject, body))
    if settings.webhook_url:
        tasks.append(_post_webhook(result, reading))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.warning("Notification delivery error: %s", r)


async def _send_email(subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg.set_content(body)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _smtp_send, msg)


def _smtp_send(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_user:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def _post_webhook(result: RuleResult, reading: TelemetryReading) -> None:
    payload = {
        "rule": result.rule,
        "action": result.action,
        "severity": result.severity,
        "device_id": reading.device_id,
        "vehicle_id": reading.vehicle_id,
        "client_id": reading.client_id,
        "ts": reading.ts.isoformat(),
        "detail": result.detail,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.webhook_url, json=payload)
        resp.raise_for_status()
