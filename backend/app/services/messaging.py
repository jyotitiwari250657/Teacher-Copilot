"""Outbound parent messaging.

The single hard rule of this module: **a message is never sent unless a teacher
has explicitly approved it.** ``send_message`` refuses anything that is not in
``approved`` status, no matter how it was called.

Delivery is SIMULATED by default. Real delivery needs explicit env configuration
and is still gated behind approval:

* ``MESSAGING_MODE=simulated`` (default) - record the send in the database with
  status ``simulated_sent`` and log the full text. Nothing leaves the machine.
* ``MESSAGING_MODE=smtp``              - real email over SMTP.
* ``MESSAGING_MODE=twilio``            - real WhatsApp via a Twilio-style API.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from ..config import settings
from ..models import ParentMessage

logger = logging.getLogger("teachercopilot.messaging")

# Only these states may be handed to a transport.
SENDABLE_STATUSES = {"approved"}


class SendNotAllowed(RuntimeError):
    """Raised when someone tries to send a message the teacher has not approved."""


@dataclass
class SendResult:
    ok: bool
    status: str
    detail: str
    provider: str = "simulated"


def can_send(message: ParentMessage) -> tuple[bool, str]:
    """The approval gate. Returns ``(allowed, reason)``."""
    if message.status not in SENDABLE_STATUSES:
        return False, (
            f"Message {message.id} is '{message.status}'. A teacher must approve a "
            f"message before it can be sent."
        )
    return True, "approved"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _deliver_simulated(message: ParentMessage) -> SendResult:
    logger.info(
        "[SIMULATED %s] to student_id=%s :: %s",
        message.channel,
        message.student_id,
        (message.subject or message.body)[:200],
    )
    return SendResult(
        ok=True,
        status="simulated_sent",
        detail="Simulated send - no real message left this machine.",
        provider="simulated",
    )


def _deliver_email(message: ParentMessage, *, to_email: str) -> SendResult:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        return SendResult(
            ok=False,
            status="failed",
            detail=(
                "SMTP is not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD, "
                "or use MESSAGING_MODE=simulated."
            ),
            provider="smtp",
        )
    if not to_email:
        return SendResult(
            ok=False, status="failed", detail="No parent email address on file.",
            provider="smtp",
        )

    email = EmailMessage()
    email["From"] = settings.smtp_from
    email["To"] = to_email
    email["Subject"] = message.subject or "Update from your child's teacher"
    email.set_content(message.body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(email)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP send failed: %s", exc)
        return SendResult(ok=False, status="failed", detail=f"SMTP error: {exc}", provider="smtp")

    return SendResult(ok=True, status="sent", detail=f"Emailed to {to_email}.", provider="smtp")


def _deliver_whatsapp(message: ParentMessage, *, to_phone: str) -> SendResult:
    if not (settings.whatsapp_account_sid and settings.whatsapp_auth_token):
        return SendResult(
            ok=False,
            status="failed",
            detail=(
                "WhatsApp is not configured. Set WHATSAPP_ACCOUNT_SID and "
                "WHATSAPP_AUTH_TOKEN, or use MESSAGING_MODE=simulated."
            ),
            provider="twilio",
        )
    if not to_phone:
        return SendResult(ok=False, status="failed", detail="No parent phone on file.",
                          provider="twilio")

    import httpx

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.whatsapp_account_sid}/Messages.json"
    )
    payload = {
        "From": settings.whatsapp_from,
        "To": f"whatsapp:{to_phone}",
        "Body": message.body,
    }
    auth = (settings.whatsapp_account_sid, settings.whatsapp_auth_token)
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, data=payload, auth=auth)
        if response.status_code >= 400:
            return SendResult(
                ok=False,
                status="failed",
                detail=f"Provider error {response.status_code}: {response.text[:200]}",
                provider="twilio",
            )
    except Exception as exc:  # noqa: BLE001
        return SendResult(ok=False, status="failed", detail=f"Network error: {exc}",
                          provider="twilio")

    return SendResult(ok=True, status="sent", detail=f"WhatsApp sent to {to_phone}.",
                      provider="twilio")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def send_message(
    message: ParentMessage,
    *,
    to_email: str = "",
    to_phone: str = "",
    force_simulate: bool = False,
) -> SendResult:
    """Deliver ONE approved message. Raises if it is not approved."""
    allowed, reason = can_send(message)
    if not allowed:
        raise SendNotAllowed(reason)

    mode = "simulated" if force_simulate else settings.messaging_mode.lower()

    if message.channel == "email":
        if mode == "smtp" and not force_simulate:
            return _deliver_email(message, to_email=to_email)
        return _deliver_simulated(message)

    # whatsapp
    if mode == "twilio" and not force_simulate:
        return _deliver_whatsapp(message, to_phone=to_phone)
    return _deliver_simulated(message)


def provider_summary() -> dict[str, object]:
    """What the Settings page shows about outbound messaging."""
    mode = settings.messaging_mode.lower()
    return {
        "mode": mode,
        "simulated": mode == "simulated",
        "smtp_configured": bool(
            settings.smtp_host and settings.smtp_user and settings.smtp_password
        ),
        "whatsapp_configured": bool(
            settings.whatsapp_account_sid and settings.whatsapp_auth_token
        ),
        "note": (
            "Messages are simulated: nothing is actually sent. Approval is still "
            "required before a simulated send is recorded."
        ),
    }
