"""
Email notifications for counselor-facing Crisis/High severity alerts.

Fires once per NEW alert (not on every update to an existing one) so a
counselor gets a single "something needs attention" email rather than being
spammed as a distressed conversation continues. This is on top of, not
instead of, the Counselor Dashboard's Alerts list — the dashboard stays the
system of record, this is just the "someone needs to look at this now" nudge
that closes the "who's actually watching?" operational-readiness gap.

Configuration (all via environment variables — see .env.example):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD  — SMTP credentials
    ALERT_FROM_EMAIL                                 — "From" address (defaults to SMTP_USER)
    COUNSELOR_ALERT_EMAILS                           — comma-separated recipient list
    FRONTEND_URL                                     — used to build a direct dashboard link

If SMTP_HOST/SMTP_USER/SMTP_PASSWORD/COUNSELOR_ALERT_EMAILS aren't all set,
sending is silently skipped (so this never breaks local dev and never blocks
the chat pipeline that calls it) — a warning is printed once so the gap is
visible in logs rather than silently swallowed.
"""
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL") or SMTP_USER
COUNSELOR_ALERT_EMAILS = [
    e.strip() for e in os.getenv("COUNSELOR_ALERT_EMAILS", "").split(",") if e.strip()
]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

_warned_not_configured = False


def _configured() -> bool:
    global _warned_not_configured
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD and COUNSELOR_ALERT_EMAILS:
        return True
    if not _warned_not_configured:
        print(
            "[notifications] SMTP not configured (need SMTP_HOST, SMTP_USER, "
            "SMTP_PASSWORD, COUNSELOR_ALERT_EMAILS) — Crisis/High alerts will "
            "NOT be emailed. Dashboard alerts still work as before."
        )
        _warned_not_configured = True
    return False


def send_counselor_alert_email(
    session_id: str,
    severity: str,
    intent: str,
    message: str,
) -> bool:
    """Best-effort — never raises, so a broken/missing SMTP config can never
    take down the chat pipeline that triggers this. Returns True if sent."""
    if not _configured():
        return False

    subject = f"[GAIDA] {severity} alert — session {session_id[:8]}"
    dashboard_link = f"{FRONTEND_URL}/counselor-dashboard"
    body = (
        f"A {severity}-severity alert was just raised in GAIDA.\n\n"
        f"Session ID: {session_id}\n"
        f"Detected intent: {intent}\n"
        f"Message: {message}\n\n"
        f"Open the Counselor Dashboard to review and respond:\n{dashboard_link}\n"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_FROM_EMAIL
    msg["To"] = ", ".join(COUNSELOR_ALERT_EMAILS)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_FROM_EMAIL, COUNSELOR_ALERT_EMAILS, msg.as_string())
        return True
    except Exception as e:
        print(f"[notifications] failed to send counselor alert email: {e}")
        return False
