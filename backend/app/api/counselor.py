"""
Counselor API routes: alerts, live sessions, chat mirroring/typing indicators,
counselor takeover/handoff, session notes, analytics, and PDF export.
"""

from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response as FastAPIResponse
from app.utils.auth import get_current_user, require_role
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

router = APIRouter(prefix="/api/counselor", tags=["counselor"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEVERITY_MAP = {
    0: "Normal",
    1: "Low",
    3: "Moderate",
    5: "High",
}

# ---------------------------------------------------------------------------
# In-memory stores
#
# NOTE: These reset on process restart and are not safe across multiple
# workers/instances. They are mirrored into Supabase best-effort, but the
# in-memory copy is the source of truth for live/active session state.
# ---------------------------------------------------------------------------
ALERTS: list[dict] = []
TYPING_STATES: dict = {}  # { session_id: { "counselor": bool, "student": bool } }

# ---------------------------------------------------------------------------
# Escalation deadlines — enforced server-side (not just a dashboard badge) so
# a Crisis/High alert that nobody has acknowledged keeps getting re-notified
# and is marked overdue. Thresholds mirror the frontend's client-side timer.
# ---------------------------------------------------------------------------
ESCALATION_THRESHOLDS_MINUTES = {
    "warning": {"work": 10, "off_hours": 5},
    "urgent":  {"work": 30, "off_hours": 15},
    "overdue": {"work": 60, "off_hours": 45},
}
ESCALATION_RE_NOTIFY_MINUTES = 30  # min between re-notification emails per alert

_PENDING_HYDRATED = False            # have ALERTS been rehydrated from Supabase?
_ESCALATION_MONITOR_STARTED = False  # background deadline thread started?
_ESCALATION_STATE_PERSISTED: set = set()  # (session_id, level, needs_supervisor) already synced


def _is_off_hours(now: datetime) -> bool:
    return now.hour < 8 or now.hour >= 17 or now.weekday() >= 5


def _parse_utc(value):
    """Parse a timestamp (ISO string or datetime) into a timezone-aware UTC
    datetime. Naive values are treated as UTC so age math never mixes naive
    and aware datetimes (which previously raised TypeError). Tolerates both
    styles seen in the wild: trailing "Z" or an explicit "+00:00" offset."""
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if s.endswith("Z"):
            # "…Z" → "…+00:00"; if an offset is already present, drop the Z.
            s = s[:-1] + "+00:00" if not re.search(r"[+-]\d{2}:?\d{2}$", s[:-1]) else s[:-1]
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _alert_age_minutes(alert: dict, now: datetime) -> int:
    # Escalation runs off the FIRST time this alert needed attention, not the
    # latest message: `timestamp` is refreshed on every student message (so the
    # dashboard shows fresh activity), while `first_alerted_at` is frozen at
    # creation. Without this, a student who keeps chatting would silently reset
    # the escalation deadline forever.
    ts = alert.get("first_alerted_at") or alert.get("timestamp") or alert.get("created_at")
    if not ts:
        return 0
    try:
        return max(0, int((now - _parse_utc(ts)).total_seconds() // 60))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Alert persistence helpers — keep the in-memory ALERTS list (dashboard source
# of truth) and the Supabase counselor_alerts table in agreement, and make
# alerts survive a backend restart.
# ---------------------------------------------------------------------------
def _row_to_alert(row: dict) -> dict:
    """Normalize a counselor_alerts DB row into the in-memory alert shape."""
    return {
        "timestamp": row.get("created_at") or (datetime.now(timezone.utc).isoformat() + "Z"),
        # Frozen age anchor for escalation deadlines — created_at never changes.
        "first_alerted_at": row.get("created_at") or row.get("timestamp"),
        "session_id": row.get("session_id"),
        "user_id": row.get("user_id"),
        "intent": row.get("intent"),
        "anxiety_score": row.get("anxiety_score") or 0,
        "severity": row.get("severity"),
        "message": row.get("message") or "",
        "last_message": row.get("message") or "",
        "status": row.get("status") or "pending",
        "counselor_took_over": bool(row.get("counselor_took_over")),
        "acknowledged": bool(row.get("acknowledged")),
        "acknowledged_at": row.get("acknowledged_at"),
        "acknowledged_by": row.get("acknowledged_by"),
        "deleted": bool(row.get("deleted")),
        "deleted_at": row.get("deleted_at"),
        "deleted_by": row.get("deleted_by"),
        "escalation_level": row.get("escalation_level") or "normal",
        "needs_supervisor": bool(row.get("needs_supervisor")),
    }


def _hydrate_alerts():
    """Pull pending alerts from Supabase into the in-memory ALERTS list so a
    backend restart can't make an unacknowledged Crisis/High alert vanish from
    the counselor dashboard. Idempotent per process: runs at startup and
    lazily on the first alerts read."""
    global _PENDING_HYDRATED
    if _PENDING_HYDRATED:
        return
    try:
        from app.database.database import supabase

        result = (
            supabase.table("counselor_alerts")
            .select("*")
            .eq("status", "pending")
            .execute()
        )
    except Exception as e:
        print(f"[counselor] alert hydration skipped: {e}")
        return

    existing_ids = {a["session_id"] for a in ALERTS}
    for row in result.data or []:
        sid = row.get("session_id")
        if not sid or sid in existing_ids:
            continue
        ALERTS.append(_row_to_alert(row))
        existing_ids.add(sid)
    _PENDING_HYDRATED = True
    if result.data:
        print(f"[counselor] rehydrated {len(result.data)} pending alert(s) from Supabase")


def _find_pending_alert_in_db(session_id: str) -> Optional[dict]:
    """Best-effort lookup of a pending DB alert for this session (used to avoid
    duplicate rows/emails when the in-memory list was reset by a restart)."""
    try:
        from app.database.database import supabase

        result = (
            supabase.table("counselor_alerts")
            .select("*")
            .eq("session_id", session_id)
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Escalation deadline monitor
# ---------------------------------------------------------------------------
def run_escalation_checks(now: Optional[datetime] = None) -> dict:
    """Enforce alert escalation deadlines (server-side, not just a badge).

    For every pending, unacknowledged Crisis/High alert: mark its
    escalation_level (normal → warning → urgent → overdue), re-fire the
    counselor email whenever it is urgent/overdue and hasn't been re-notified
    recently, and flag overdue alerts as needing a supervisor. Keeps running
    until the alert is acknowledged, handed over, or resolved."""
    now = now or datetime.now(timezone.utc)
    off = _is_off_hours(now)
    bucket = "off_hours" if off else "work"
    renotified = 0
    overdue_now = 0
    normal_reset = 0

    for alert in ALERTS:
        if alert.get("status") != "pending" or alert.get("acknowledged"):
            if alert.get("escalation_level") not in (None, "normal") or alert.get("needs_supervisor"):
                alert["escalation_level"] = "normal"
                alert["needs_supervisor"] = False
                normal_reset += 1
                _persist_escalation_state(alert)
            continue

        if alert.get("severity") not in ("High", "Crisis"):
            continue

        age = _alert_age_minutes(alert, now)
        warn_m = ESCALATION_THRESHOLDS_MINUTES["warning"][bucket]
        urg_m = ESCALATION_THRESHOLDS_MINUTES["urgent"][bucket]
        over_m = ESCALATION_THRESHOLDS_MINUTES["overdue"][bucket]

        if age >= over_m:
            level = "overdue"
        elif age >= urg_m:
            level = "urgent"
        elif age >= warn_m:
            level = "warning"
        else:
            level = "normal"

        alert["escalation_level"] = level
        alert["age_minutes"] = age
        alert["is_off_hours"] = off

        if level == "overdue":
            alert["needs_supervisor"] = True
            overdue_now += 1

        if level in ("urgent", "overdue") and not _notified_recently(alert, now):
            _notify_escalation(alert, level, off)
            renotified += 1

        _persist_escalation_state(alert)

    return {
        "checked": len(ALERTS),
        "renotified": renotified,
        "overdue": overdue_now,
        "off_hours": off,
        "reset": normal_reset,
    }


def _notified_recently(alert: dict, now: datetime) -> bool:
    last = alert.get("last_escalation_email_at")
    if not last:
        return False
    try:
        return (now - _parse_utc(last)).total_seconds() < ESCALATION_RE_NOTIFY_MINUTES * 60
    except (ValueError, TypeError):
        return False


def _notify_escalation(alert: dict, level: str, off_hours: bool):
    try:
        from app.services.notifications import send_escalation_email

        ok = send_escalation_email(alert, level, off_hours=off_hours)
    except Exception as e:
        print(f"[counselor] escalation email failed: {e}")
        ok = False

    at = datetime.now(timezone.utc).isoformat() + "Z"
    alert["last_escalation_email_at"] = at
    alert.setdefault("notifications", []).append(
        {"at": at, "level": level, "channel": "email", "outcome": "sent" if ok else "failed"}
    )
    alert["notifications"] = alert["notifications"][-20:]


def _persist_escalation_state(alert: dict):
    """Best-effort, throttled sync of escalation state to Supabase so the
    dashboard can trust server state after a restart. Column-missing errors
    are non-fatal (same policy as the acknowledge handler)."""
    key = (alert["session_id"], alert.get("escalation_level"), bool(alert.get("needs_supervisor")))
    if key in _ESCALATION_STATE_PERSISTED:
        return
    try:
        from app.database.database import supabase

        supabase.table("counselor_alerts").update(
            {
                "escalation_level": alert.get("escalation_level") or "normal",
                "needs_supervisor": bool(alert.get("needs_supervisor")),
                "age_minutes": alert.get("age_minutes") or 0,
            }
        ).eq("session_id", alert["session_id"]).execute()
        _ESCALATION_STATE_PERSISTED.add(key)
    except Exception:
        # Column may not exist yet in Supabase — visibility/email still work.
        pass


def _start_escalation_monitor(interval_seconds: int = 60):
    """Daemon background loop enforcing escalation deadlines. Single-process
    (matches the documented single-instance deployment assumption)."""
    global _ESCALATION_MONITOR_STARTED
    if _ESCALATION_MONITOR_STARTED:
        return
    _ESCALATION_MONITOR_STARTED = True

    def _loop():
        while True:
            try:
                run_escalation_checks()
            except Exception as e:
                print(f"[counselor] escalation check error: {e}")
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, name="gaida-escalation-monitor", daemon=True).start()
    print("[counselor] escalation deadline monitor started")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AlertStatusUpdate(BaseModel):
    session_id: str
    status: str


class AlertAcknowledge(BaseModel):
    session_id: str
    counselor_id: Optional[str] = None


class TakeOverMessage(BaseModel):
    session_id: str
    message: str
    counselor_id: Optional[str] = None


class TypingPayload(BaseModel):
    is_typing: bool
    sender: str  # "counselor" or "student"


class StudentMessage(BaseModel):
    sender: str
    text: str


class CounselorRequest(BaseModel):
    session_id: str
    message: str = ""


class SessionNote(BaseModel):
    session_id: str
    note: str
    outcome: str  # e.g. "resolved", "false_alarm", "referred", "follow_up_scheduled"


class ResolveSession(BaseModel):
    session_id: str
    resolved_by: Optional[str] = None

class DeleteCases(BaseModel):
    session_id: str
    deleted_by: Optional[str] = None

class SessionRating(BaseModel):
    session_id: str
    wellbeing_rating: int
    severity_at_end: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_severity(anxiety_score: int) -> str:
    return SEVERITY_MAP.get(anxiety_score, "Normal")


def should_alert_counselor(severity: str) -> bool:
    return severity in ("High", "Crisis")


def require_session_owner(session_id: str, user: dict):
    """403 unless the authenticated user owns the given session (or the
    session has no recorded owner). Counselors are allowed to read any
    session, so this check is skipped for role == counselor."""
    if user.get("role") == "counselor":
        return

    from app.services.session_manager import get_session

    session = get_session(session_id)
    if session and session.get("user_id") and session["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")


def process_alert(
    session_id: str,
    user_id: Optional[str],
    intent: str,
    anxiety_score: int,
    message: str,
    severity: Optional[str] = None,
) -> dict:
    """Called by intent_router.py after each analyzed student message."""
    if severity is None:
        severity = get_severity(anxiety_score)
    alert_sent = False

    if should_alert_counselor(severity):
        existing = next((a for a in ALERTS if a["session_id"] == session_id), None)
        if existing is None:
            # The in-memory list may be empty after a restart — reuse a
            # pending alert that already exists in the DB for this session
            # instead of creating a duplicate row + duplicate email.
            db_row = _find_pending_alert_in_db(session_id)
            if db_row:
                existing = _row_to_alert(db_row)
                ALERTS.append(existing)

        if existing:
            existing["last_message"] = message
            existing["timestamp"] = datetime.utcnow().isoformat() + "Z"
            existing["intent"] = intent
            # Keep the original age anchor (do NOT let new messages reset the
            # escalation deadline).
            existing.setdefault("first_alerted_at", existing["timestamp"])
        else:
            alert_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "first_alerted_at": datetime.utcnow().isoformat() + "Z",
                "session_id": session_id,
                "user_id": user_id,
                "intent": intent,
                "anxiety_score": anxiety_score,
                "severity": severity,
                "message": message,
                "last_message": message,
                "status": "pending",
                "counselor_took_over": False,
                "acknowledged": False,
                "acknowledged_at": None,
                "acknowledged_by": None,
            }
            ALERTS.append(alert_entry)

            try:
                from app.database.database import supabase

                supabase.table("counselor_alerts").insert(
                    {
                        "session_id": session_id,
                        "user_id": user_id or session_id,
                        "intent": intent,
                        "anxiety_score": anxiety_score,
                        "severity": severity,
                        "message": message,
                        "status": "pending",
                    }
                ).execute()
            except Exception as e:
                print(f"Supabase alert insert error: {e}")

            # Email the counselor(s) on file — best-effort, never raises, and
            # only fires for a brand-new alert (not on every update to an
            # existing one) so an ongoing distressed conversation doesn't
            # spam the inbox. See app/services/notifications.py.
            try:
                from app.services.notifications import send_counselor_alert_email

                send_counselor_alert_email(
                    session_id=session_id,
                    severity=severity,
                    intent=intent,
                    message=message,
                )
            except Exception as e:
                print(f"[counselor] alert email dispatch failed: {e}")

        alert_sent = True

    return {
        "severity": severity,
        "alert_sent": alert_sent,
    }


# ===========================================================================
# Alerts
# ===========================================================================
@router.get("/student/checkin/{student_id}")
def get_checkin_status(student_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "counselor" and user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Not allowed to view this student's check-in status")
    try:
        from app.database.database import supabase
        result = supabase.table("sessions")\
            .select("session_token, peak_severity, created_at")\
            .eq("student_id", student_id)\
            .not_.is_("ended_at", "null")\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        if not result.data:
            return {"needs_checkin": False}

        last = result.data[0]
        peak = last.get("peak_severity", "Normal")

        if peak in ("High", "Crisis"):
            return {
                "needs_checkin": True,
                "peak_severity": peak,
                "last_session": last.get("created_at"),
            }

        return {"needs_checkin": False}
    except Exception as e:
        return {"needs_checkin": False, "error": str(e)}
    
@router.post("/session/rate")
def rate_session(payload: SessionRating, user: dict = Depends(get_current_user)):
    require_session_owner(payload.session_id, user)
    try:
        from app.database.database import supabase
        supabase.table("session_ratings").insert({
            "session_id": payload.session_id,
            "wellbeing_rating": payload.wellbeing_rating,
            "severity_at_end": payload.severity_at_end,
            "rated_at": datetime.utcnow().isoformat() + "Z",
        }).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/alerts")
def get_alerts(user: dict = Depends(require_role("counselor"))):
    _hydrate_alerts()
    visible = [a for a in ALERTS if not a.get("deleted")]
    return {"alerts": visible, "count": len(visible)}


@router.get("/alerts/pending")
def get_pending_alerts(user: dict = Depends(require_role("counselor"))):
    _hydrate_alerts()
    pending = [a for a in ALERTS if a.get("status") == "pending" and not a.get("deleted")]
    return {"alerts": pending, "count": len(pending)}


@router.post("/alerts/update")
def update_alert_status(payload: AlertStatusUpdate, user: dict = Depends(require_role("counselor"))):
    for alert in ALERTS:
        if alert["session_id"] == payload.session_id:
            # Crisis/High alerts must be explicitly acknowledged (see
            # /alerts/acknowledge) before they can be moved off "pending" —
            # otherwise a counselor could silently clear the highest-risk
            # alerts without ever confirming they saw one.
            if (
                alert.get("severity") in ("High", "Crisis")
                and not alert.get("acknowledged")
                and payload.status != "pending"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="This Crisis/High alert must be acknowledged before it can be updated.",
                )

            alert["status"] = payload.status
            alert["updated_at"] = datetime.utcnow().isoformat() + "Z"
            try:
                from app.database.database import supabase

                supabase.table("counselor_alerts").update(
                    {"status": payload.status}
                ).eq("session_id", payload.session_id).execute()
            except Exception as e:
                print(f"Supabase alert update error: {e}")
            return {"ok": True}
    return {"ok": False, "error": "Alert not found"}


@router.post("/alerts/acknowledge")
def acknowledge_alert(payload: AlertAcknowledge, user: dict = Depends(require_role("counselor"))):
    """Explicit "I have seen this" action for Crisis/High alerts, distinct
    from resolving/reviewing them. Required before /alerts/update or
    /sessions/resolve can move a Crisis/High alert off "pending"."""
    for alert in ALERTS:
        if alert["session_id"] == payload.session_id:
            alert["acknowledged"] = True
            alert["acknowledged_at"] = datetime.utcnow().isoformat() + "Z"
            alert["acknowledged_by"] = payload.counselor_id or user.get("user_id")
            try:
                from app.database.database import supabase

                supabase.table("counselor_alerts").update(
                    {
                        "acknowledged": True,
                        "acknowledged_at": alert["acknowledged_at"],
                        "acknowledged_by": alert["acknowledged_by"],
                    }
                ).eq("session_id", payload.session_id).execute()
            except Exception as e:
                # Columns may not exist yet in Supabase — the in-memory
                # ALERTS list (used by the live dashboard) is already
                # updated above, so this failure is non-fatal.
                print(f"Supabase alert acknowledge error: {e}")
            return {"ok": True, "acknowledged_at": alert["acknowledged_at"]}
    return {"ok": False, "error": "Alert not found"}


@router.post("/request-counselor")
def request_counselor(payload: CounselorRequest, user: dict = Depends(get_current_user)):
    require_session_owner(payload.session_id, user)
    try:
        existing = next((a for a in ALERTS if a["session_id"] == payload.session_id), None)
        if existing is None:
            db_row = _find_pending_alert_in_db(payload.session_id)
            if db_row:
                existing = _row_to_alert(db_row)
                ALERTS.append(existing)

        if existing:
            existing["last_message"] = payload.message
            existing["timestamp"] = datetime.utcnow().isoformat() + "Z"
            existing.setdefault("first_alerted_at", existing["timestamp"])
        else:
            alert_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "first_alerted_at": datetime.utcnow().isoformat() + "Z",
                "session_id": payload.session_id,
                "user_id": None,
                "intent": "student_requested",
                "anxiety_score": 0,
                "severity": "Requested",
                "message": payload.message,
                "last_message": payload.message,
                "status": "pending",
                "counselor_took_over": False,
                "acknowledged": False,
                "acknowledged_at": None,
                "acknowledged_by": None,
            }
            ALERTS.append(alert_entry)

            try:
                from app.database.database import supabase

                supabase.table("counselor_alerts").insert(
                    {
                        "session_id": payload.session_id,
                        "user_id": payload.session_id,
                        "intent": "student_requested",
                        "anxiety_score": 0,
                        "severity": "Requested",
                        "message": payload.message,
                        "status": "pending",
                    }
                ).execute()
            except Exception as e:
                print(f"Supabase alert insert error: {e}")

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/severity/{anxiety_score}")
def check_severity(anxiety_score: int, user: dict = Depends(get_current_user)):
    severity = get_severity(anxiety_score)
    return {
        "anxiety_score": anxiety_score,
        "severity": severity,
        "requires_alert": should_alert_counselor(severity),
    }


# ===========================================================================
# Live / active sessions
# ===========================================================================
# Sessions a counselor has already performed a welfare check on this process,
# so repeated polling doesn't re-flag the same student every refresh (clears
# on backend restart).
_WELFARE_CHECKED: set[str] = set()


@router.get("/sessions/welfare")
def get_welfare_checks(user: dict = Depends(require_role("counselor"))):
    """At-risk students who went silent: High/Crisis sessions with no activity
    for WELFARE_CHECK_MINUTES. Surfaces silently-abandoned sessions so a human
    can actively check on them, instead of them just disappearing from active."""
    try:
        from app.services.session_manager import get_sessions_needing_welfare_check

        sessions = get_sessions_needing_welfare_check()
        pending = [s for s in sessions if s["session_id"] not in _WELFARE_CHECKED]
        return {"sessions": pending, "count": len(pending)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


class WelfareCheckRequest(BaseModel):
    session_id: str


@router.post("/sessions/welfare-checked")
def mark_welfare_checked(payload: WelfareCheckRequest, user: dict = Depends(require_role("counselor"))):
    _WELFARE_CHECKED.add(payload.session_id)
    return {"ok": True}


@router.get("/sessions/active")
def get_active_sessions(user: dict = Depends(require_role("counselor"))):
    try:
        from app.services.session_manager import list_active_sessions

        sessions = list_active_sessions()
        result = []
        for s in sessions:
            meta = s.get("meta", {})

            # Skip resolved sessions
            if meta.get("resolved"):
                continue

            # record_interaction stores the session's worst state in
            # peak_severity; reading meta["severity"] (never written) made every
            # session fall through to the confidence heuristic below and no
            # session could ever display as Crisis.
            severity = meta.get("peak_severity") or meta.get("severity") or "Normal"
            confidence = meta.get("running_confidence", 0.3)

            if not severity or severity == "Normal":
                if confidence >= 0.75:
                    severity = "High"
                elif confidence >= 0.60:
                    severity = "Moderate"
                elif confidence >= 0.45:
                    severity = "Low"
                else:
                    severity = "Normal"

            has_alert = any(
                a["session_id"] == s["session_id"]
                and a["status"] == "pending"
                and not a.get("deleted")
                for a in ALERTS
            )

            result.append(
                {
                    "session_id": s["session_id"],
                    "started_at": s.get("started_at"),
                    "message_count": len(s.get("messages", [])),
                    "severity": severity,
                    "confidence": round(confidence, 3),
                    "intent": meta.get("running_intent", "neutral"),
                    "has_alert": has_alert,
                    "active": s.get("active", True),
                    "assigned_counselor_id": meta.get("assigned_counselor_id"),
                }
            )

        return {"sessions": result, "count": len(result)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


@router.post("/sessions/resolve")
def resolve_session(payload: ResolveSession, user: dict = Depends(require_role("counselor"))):
    try:
        from app.services.session_manager import get_session

        session = get_session(payload.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Same Crisis/High acknowledgment gate as /alerts/update — resolving
        # a session is another way to clear its alert, so it needs the same
        # "a human actually saw this" check.
        matching_alert = next((a for a in ALERTS if a["session_id"] == payload.session_id), None)
        if (
            matching_alert
            and matching_alert.get("severity") in ("High", "Crisis")
            and not matching_alert.get("acknowledged")
        ):
            raise HTTPException(
                status_code=400,
                detail="This Crisis/High alert must be acknowledged before the session can be resolved.",
            )

        if "meta" not in session:
            session["meta"] = {}
        session["meta"]["resolved"] = True
        session["meta"]["resolved_at"] = datetime.utcnow().isoformat() + "Z"
        session["meta"]["resolved_by"] = payload.resolved_by

        # Also mark the alert as resolved
        for alert in ALERTS:
            if alert["session_id"] == payload.session_id:
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.utcnow().isoformat() + "Z"

        try:
            from app.database.database import supabase

            supabase.table("counselor_alerts").update({"status": "resolved"}).eq(
                "session_id", payload.session_id
            ).execute()

            supabase.table("sessions").update(
                {
                    "resolved": True,
                    "resolved_at": datetime.utcnow().isoformat() + "Z",
                    "resolved_by": payload.resolved_by,
                }
            ).eq("session_token", payload.session_id).execute()
        except Exception as e:
            print(f"Supabase resolve error: {e}")

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/sessions/resolved")
def get_resolved_sessions(user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase
        from app.constants import TEST_CREDENTIALS

        alerts = (
        supabase.table("counselor_alerts")
        .select("*")
        .eq("status", "resolved")
        .eq("deleted", False)   # ← added
        .order("created_at", desc=True)
        .execute()
    )

        result = []
        for alert in alerts.data:
            session_id = alert.get("session_id")
            student_id = alert.get("user_id")

            notes = (
                supabase.table("session_notes")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            interactions = (
                supabase.table("interactions")
                .select("*")
                .eq("session_id", session_id)
                .order("timestamp")
                .execute()
            )

            creds = TEST_CREDENTIALS.get(student_id, {})
            profile = (
                {
                    "student_id": student_id,
                    "name": creds.get("name"),
                    "program": creds.get("program"),
                    "year": creds.get("year"),
                    "email": creds.get("email"),
                }
                if creds
                else None
            )

            # Build a labeled transcript. A stored row is one user turn +
            # GAIDA's reply in `response`; counselor takeover messages and
            # system notices are rows whose message text carries no GAIDA
            # reply. Distinguish them by intent: counselor_intervention = a
            # counselor, otherwise intent None = a system notice, else it's
            # a user turn (with GAIDA's reply if present).
            transcript = []
            for row in interactions.data:
                ts = row.get("timestamp")
                msg = row.get("message") or ""
                if row.get("intent") == "counselor_intervention":
                    transcript.append({"sender": "counselor", "text": msg, "timestamp": ts})
                elif row.get("intent") is None and msg:
                    transcript.append({"sender": "system", "text": msg, "timestamp": ts})
                else:
                    transcript.append({"sender": "user", "text": msg, "timestamp": ts})
                    if row.get("response"):
                        transcript.append({"sender": "bot", "text": row["response"], "timestamp": ts})

            result.append(
                {
                    "session_id": session_id,
                    "student_id": student_id,
                    "profile": profile,
                    "severity": alert.get("severity"),
                    "intent": alert.get("intent"),
                    "timestamp": alert.get("created_at"),
                    "resolved_at": alert.get("resolved_at"),
                    "note": notes.data[0] if notes.data else None,
                    "transcript": transcript,
                }
            )

        return {"sessions": result, "count": len(result)}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


# ===========================================================================
# Chat mirroring / typing indicators
# ===========================================================================
@router.get("/chat/{session_id}")
def get_chat_transcript(session_id: str, user: dict = Depends(get_current_user)):
    """
    Returns full chat transcript including student messages mirrored via
    POST /chat/{session_id}. Also returns typing state for both parties.
    """
    require_session_owner(session_id, user)
    try:
        from app.services.session_manager import get_session

        session = get_session(session_id)
        if not session:
            return {
                "error": "Session not found",
                "messages": [],
                "counselor_typing": False,
                "student_typing": False,
            }

        messages = []
        for m in session.get("messages", []):
            messages.append(
                {
                    "sender": m.get("sender"),
                    "text": m.get("text"),
                    "timestamp": m.get("timestamp"),
                    "intent": m.get("analysis", {}).get("intent"),
                    "confidence": m.get("analysis", {}).get("confidence"),
                }
            )

        typing = TYPING_STATES.get(session_id, {})

        return {
            "session_id": session_id,
            "user_id": session.get("user_id"),
            "messages": messages,
            "severity": session.get("meta", {}).get("running_confidence", 0.3),
            "counselor_typing": typing.get("counselor", False),
            "student_typing": typing.get("student", False),
            "counselor_active": session.get("meta", {}).get("counselor_active", False),
            "assigned_counselor_id": session.get("meta", {}).get("assigned_counselor_id"),
        }
    except Exception as e:
        return {"error": str(e), "messages": [], "counselor_typing": False, "student_typing": False}




@router.post("/typing/{session_id}")
def set_typing(session_id: str, payload: TypingPayload, user: dict = Depends(get_current_user)):
    """Set typing indicator for counselor or student."""
    require_session_owner(session_id, user)
    if session_id not in TYPING_STATES:
        TYPING_STATES[session_id] = {"counselor": False, "student": False}
    TYPING_STATES[session_id][payload.sender] = payload.is_typing
    return {"ok": True}


# ===========================================================================
# Counselor takeover / handoff
# ===========================================================================
@router.post("/takeover")
def counselor_takeover(payload: TakeOverMessage, user: dict = Depends(require_role("counselor"))):
    """
    Counselor sends a message directly to the student.
    Sets counselor_active = True so the VA stops responding.
    """
    try:
        from app.services.session_manager import get_session, record_interaction

        session = get_session(payload.session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}

        if "meta" not in session:
            session["meta"] = {}

        # Block if already assigned to a different counselor
        assigned = session["meta"].get("assigned_counselor_id")
        if assigned and assigned != payload.counselor_id:
            return {"ok": False, "error": "already_assigned", "assigned_to": assigned}

        session["meta"]["counselor_active"] = True
        session["meta"]["counselor_message"] = payload.message
        session["meta"]["assigned_counselor_id"] = payload.counselor_id

        record_interaction(
            session_id=payload.session_id,
            sender="counselor",
            text=payload.message,
            analysis={"intent": "counselor_intervention"},
            response=None,
        )

        for alert in ALERTS:
            if alert["session_id"] == payload.session_id:
                alert["status"] = "escalated"
                alert["counselor_took_over"] = True
                break

        # Mirror the status change to Supabase so the DB row matches the
        # in-memory state (otherwise a restart flips the alert back to pending).
        try:
            from app.database.database import supabase

            supabase.table("counselor_alerts").update(
                {"status": "escalated", "counselor_took_over": True}
            ).eq("session_id", payload.session_id).execute()
        except Exception as e:
            print(f"[counselor] takeover alert persist error: {e}")

        return {"ok": True, "message": payload.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/return-to-gaida")
def return_to_gaida(payload: dict, user: dict = Depends(require_role("counselor"))):
    try:
        from app.services.session_manager import get_session, record_interaction

        session_id = payload.get("session_id")
        session = get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if "meta" not in session:
            session["meta"] = {}

        # Only the counselor who took over may hand the session back — without
        # this, counselor B could silently yank a session counselor A is
        # actively handling.
        assigned = session["meta"].get("assigned_counselor_id")
        caller = (payload.get("counselor_id") or "").strip() or user.get("user_id")
        if assigned and caller and assigned != caller:
            return {"ok": False, "error": "already_assigned", "assigned_to": assigned}

        session["meta"]["counselor_active"] = False
        session["meta"]["assigned_counselor_id"] = None

        record_interaction(
            session_id=session_id,
            sender="system",
            text="Counselor returned the conversation to GAIDA.",
            analysis={},
            response=None,
        )

        return {"ok": True, "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ===========================================================================
# Session notes
# ===========================================================================
@router.post("/session-notes")
def add_session_note(payload: SessionNote, user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase

        supabase.table("session_notes").insert(
            {
                "session_id": payload.session_id,
                "note": payload.note,
                "outcome": payload.outcome,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
        ).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/session-notes/{session_id}")
def get_session_notes(session_id: str, user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase

        result = (
            supabase.table("session_notes")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"notes": result.data}
    except Exception as e:
        return {"notes": [], "error": str(e)}


# ===========================================================================
# Student profile
# ===========================================================================
@router.get("/student-profile/{student_id}")
def get_student_profile(student_id: str, user: dict = Depends(require_role("counselor"))):
    from app.constants import TEST_CREDENTIALS

    creds = TEST_CREDENTIALS.get(student_id)
    if not creds or "name" not in creds:
        return {"profile": None}
    return {
        "profile": {
            "student_id": student_id,
            "name": creds["name"],
            "email": creds["email"],
            "program": creds.get("program"),
            "year": creds.get("year"),
        }
    }


# ===========================================================================
# Analytics
# ===========================================================================
@router.get("/analytics/overview")
def get_analytics_overview(user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase
        from datetime import timedelta

        # Anxiety distribution + monthly trends from interactions
        interactions = supabase.table("interactions").select("severity, timestamp").execute()
        severity_counts = {"Low": 0, "Moderate": 0, "High": 0, "Normal": 0, "Crisis": 0}
        for row in interactions.data:
            s = row.get("severity", "Normal") or "Normal"
            if s in severity_counts:
                severity_counts[s] += 1

        # Monthly anxiety trends — rolling 12 months ending now
        def _shift_month(dt, months):
            idx = dt.year * 12 + (dt.month - 1) + months
            return datetime(idx // 12, idx % 12 + 1, 1)

        now = datetime.utcnow()
        months = [
            {
                "key": _shift_month(now, i - 11).strftime("%Y-%m"),
                "month": _shift_month(now, i - 11).strftime("%b"),
                "normal": 0,
                "low": 0,
                "moderate": 0,
                "high": 0,
                "crisis": 0,
            }
            for i in range(12)
        ]
        buckets = {m["key"]: m for m in months}
        valid_severities = ("Normal", "Low", "Moderate", "High", "Crisis")
        for row in interactions.data:
            ts = row.get("timestamp")
            s = row.get("severity")
            if not ts or s not in valid_severities:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            key = dt.strftime("%Y-%m")
            if key in buckets:
                buckets[key][s.lower()] += 1

        # Sessions this week
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        sessions = (
            supabase.table("sessions").select("created_at").gte("created_at", week_ago).execute()
        )

        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        week_data = {d: 0 for d in days}
        for row in sessions.data:
            if row.get("created_at"):
                day = datetime.fromisoformat(row["created_at"]).strftime("%a")
                if day in week_data:
                    week_data[day] += 1

        alerts = supabase.table("counselor_alerts").select("created_at, severity").execute()

        return {
            "anxiety_distribution": [
                {"name": k, "value": v} for k, v in severity_counts.items() if v > 0
            ],
            "monthly_trends": [
                {k: m[k] for k in ("month", "normal", "low", "moderate", "high", "crisis")} for m in months
            ],
            "sessions_this_week": [{"day": d, "count": week_data[d]} for d in days],
            "total_sessions": len(supabase.table("sessions").select("id").execute().data),
            "total_alerts": len(alerts.data),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/analytics/reports")
def get_analytics_reports(user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase

        # Sessions + alerts + severity counts per month — rolling 12 months
        def _shift_month(dt, months):
            idx = dt.year * 12 + (dt.month - 1) + months
            return datetime(idx // 12, idx % 12 + 1, 1)

        now = datetime.utcnow()
        months = [
            {
                "key": _shift_month(now, i - 11).strftime("%Y-%m"),
                "month": _shift_month(now, i - 11).strftime("%b"),
                "sessions": 0,
                "alerts": 0,
                "normal": 0,
                "low": 0,
                "moderate": 0,
                "high": 0,
                "crisis": 0,
            }
            for i in range(12)
        ]
        buckets = {m["key"]: m for m in months}

        def _count_by_month(rows, col):
            for row in rows:
                ts = row.get(col)
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except ValueError:
                    continue
                key = dt.strftime("%Y-%m")
                if key in buckets:
                    buckets[key][col] += 1

        _count_by_month(
            supabase.table("sessions").select("created_at").execute().data, "created_at"
        )
        _count_by_month(
            supabase.table("counselor_alerts").select("created_at").execute().data, "created_at"
        )

        # Monthly severity breakdown from interactions
        interactions = supabase.table("interactions").select("severity, timestamp").execute()
        valid_severities = ("Normal", "Low", "Moderate", "High", "Crisis")
        for row in interactions.data:
            ts = row.get("timestamp")
            s = row.get("severity")
            if not ts or s not in valid_severities:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            key = dt.strftime("%Y-%m")
            if key in buckets:
                buckets[key][s.lower()] += 1

        return {
            "monthly_reports": [
                {
                    k: m[k]
                    for k in ("month", "sessions", "alerts", "normal", "low", "moderate", "high", "crisis")
                }
                for m in months
            ],
        }
    except Exception as e:
        return {"error": str(e)}


# ===========================================================================
# PDF export
# ===========================================================================
@router.get("/export-session/{session_id}")
def export_session_pdf(session_id: str, user: dict = Depends(require_role("counselor"))):
    try:
        from app.database.database import supabase
        from app.constants import TEST_CREDENTIALS

        try:
            session_result = (
                supabase.table("sessions")
                .select("*")
                .eq("session_token", session_id)
                .single()
                .execute()
            )
        except Exception:
            session_result = None

        if not session_result or not session_result.data:
            raise HTTPException(status_code=404, detail="Session not found")

        session = session_result.data
        meta = session.get("meta") or {}

        interactions_result = (
            supabase.table("interactions")
            .select("*")
            .eq("session_id", session_id)
            .order("timestamp")
            .execute()
        )
        interactions = interactions_result.data or []

        messages = []
        for row in interactions:
            ts = row.get("timestamp")
            msg = row.get("message") or ""
            # Same sender disambiguation as Resolved Cases: a row stores one
            # user turn + GAIDA's reply in `response`, while counselor
            # takeover messages (intent=counselor_intervention) and system
            # notices (intent None, no GAIDA reply) are their own rows.
            if row.get("intent") == "counselor_intervention":
                messages.append(
                    {
                        "sender": "counselor",
                        "text": msg,
                        "timestamp": ts,
                        "analysis": {"confidence": row.get("confidence")},
                    }
                )
            elif row.get("intent") is None and msg:
                messages.append(
                    {"sender": "system", "text": msg, "timestamp": ts}
                )
            else:
                messages.append(
                    {
                        "sender": "user",
                        "text": msg,
                        "timestamp": ts,
                        "analysis": {
                            "intent": row.get("intent"),
                            "confidence": row.get("confidence"),
                        },
                    }
                )
                if row.get("response"):
                    messages.append(
                        {
                            "sender": "assistant",
                            "text": row["response"],
                            "timestamp": ts,
                        }
                    )

        user_id = session["student_id"]
        started_at = session.get("started_at") or session.get("created_at")

        creds = TEST_CREDENTIALS.get(user_id, {}) if user_id else {}
        student_name = creds.get("name", "Not identified")
        student_program = creds.get("program", "—")
        student_year = creds.get("year", "—")
        student_email = creds.get("email", "—")

        # Latest case note, if one exists
        note_text = "—"
        note_outcome = "—"
        try:
            notes = (
                supabase.table("session_notes")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if notes.data:
                note_text = notes.data[0].get("note") or "—"
                note_outcome = notes.data[0].get("outcome") or "—"
        except Exception as e:
            print(f"Note fetch error during export: {e}")

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
        meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
        label_style = ParagraphStyle(
            "Label", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#374151"),
            spaceBefore=2, spaceAfter=2,
        )

        elements = []

        # ── Header ─────────────────────────────────────────────
        elements.append(Paragraph("GAIDA — Session Referral Report", title_style))
        elements.append(Paragraph("University of the East — Guidance & Counseling Office", meta_style))
        elements.append(Spacer(1, 12))

        # ── Student info table ─────────────────────────────────
        student_data = [
            ["Student Name", student_name],
            ["Student ID", user_id or "Not identified"],
            ["Program / Year", f"{student_program}, Year {student_year}" if student_program != "—" else "—"],
            ["Email", student_email],
        ]
        student_table = Table(student_data, colWidths=[150, 350])
        student_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(student_table)
        elements.append(Spacer(1, 16))

        # ── Session metadata table ────────────────────────────
        last_confidence = meta.get("running_confidence")
        if last_confidence is None:
            try:
                # sessions table has no confidence column — use the last
                # analyzed interaction's score if available.
                conf_candidates = [r.get("confidence") for r in interactions if r.get("confidence") is not None]
                last_confidence = conf_candidates[-1] if conf_candidates else 0
            except (TypeError, IndexError):
                last_confidence = 0

        resolved_by = session.get("resolved_by") or meta.get("resolved_by") or "Not yet resolved"
        summary_data = [
            ["Session ID", session_id],
            ["Started At", started_at or "—"],
            ["Total Messages", str(len(messages))],
            ["Peak Anxiety Level", str(session.get("peak_severity") or meta.get("peak_severity") or "—")],
            ["Final Confidence Score", f"{float(last_confidence or 0):.0%}"],
            ["Resolved By", resolved_by],
            ["Outcome", note_outcome.replace("_", " ").title() if note_outcome != "—" else "—"],
            ["Case Note", note_text],
        ]
        summary_table = Table(summary_data, colWidths=[150, 350])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # ── Conversation transcript ───────────────────────────
        elements.append(Paragraph("Conversation Transcript", styles["Heading2"]))
        elements.append(Spacer(1, 8))

        sender_labels = {
            "user": "Student",
            "assistant": "GAIDA",
            "bot": "GAIDA",
            "counselor": "Counselor",
            "system": "System",
        }

        for m in messages:
            sender = sender_labels.get(m.get("sender"), m.get("sender", "Unknown"))
            text = m.get("text", "") or ""
            timestamp = m.get("timestamp", "")
            analysis = m.get("analysis", {})
            intent = analysis.get("intent")
            confidence = analysis.get("confidence")

            tag = f"<b>{sender}</b>"
            if intent and confidence is not None:
                tag += f" <font size=8 color='#9ca3af'>({intent}, {confidence:.0%})</font>"
            tag += f" <font size=7 color='#9ca3af'>{timestamp}</font>"

            elements.append(Paragraph(tag, label_style))
            elements.append(Paragraph(text.replace("\n", "<br/>"), styles["Normal"]))
            elements.append(Spacer(1, 8))

        doc.build(elements)
        buffer.seek(0)

        return FastAPIResponse(
            content=buffer.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=GAIDA_Session_{session_id[:8]}.pdf"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")
    
@router.post("/sessions/delete")
def soft_delete_cases(payload: DeleteCases, user: dict = Depends(require_role("counselor"))):
    """
    Soft delete a session and its associated data.
    Marks the session as deleted in the database and removes it from active memory.
    """
    found = False
    for alert in ALERTS:
        if alert["session_id"] == payload.session_id:
            alert["deleted"] = True
            alert["deleted_at"] = datetime.utcnow().isoformat() + "Z"
            alert["deleted_by"] = payload.deleted_by
            found = True
            break
    try:
        from app.database.database import supabase

        supabase.table("counselor_alerts").update({
            "deleted": True,
            "deleted_at": datetime.utcnow().isoformat() + "Z",
            "deleted_by": payload.deleted_by,
        }).eq("session_id", payload.session_id).execute()
    except Exception as e:
        print(f"Supabase delete error: {e}")

    if not found:
        # still return ok — the Supabase row may exist even if not in the
        # in-memory ALERTS list (e.g. after a server restart)
        return {"ok": True, "note": "not found in memory, supabase update attempted"}
    
    return {"ok": True}
