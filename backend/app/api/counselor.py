"""
Counselor API routes: alerts, live sessions, chat mirroring/typing indicators,
counselor takeover/handoff, session notes, analytics, and PDF export.
"""

from datetime import datetime
from io import BytesIO
from typing import Optional

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
# Pydantic models
# ---------------------------------------------------------------------------
class AlertStatusUpdate(BaseModel):
    session_id: str
    status: str


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

        if existing:
            existing["last_message"] = message
            existing["timestamp"] = datetime.utcnow().isoformat() + "Z"
            existing["intent"] = intent
        else:
            alert_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "session_id": session_id,
                "user_id": user_id,
                "intent": intent,
                "anxiety_score": anxiety_score,
                "severity": severity,
                "message": message,
                "last_message": message,
                "status": "pending",
                "counselor_took_over": False,
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
    return {"alerts": ALERTS, "count": len(ALERTS)}


@router.get("/alerts/pending")
def get_pending_alerts(user: dict = Depends(require_role("counselor"))):
    pending = [a for a in ALERTS if a.get("status") == "pending"]
    return {"alerts": pending, "count": len(pending)}


@router.post("/alerts/update")
def update_alert_status(payload: AlertStatusUpdate, user: dict = Depends(require_role("counselor"))):
    for alert in ALERTS:
        if alert["session_id"] == payload.session_id:
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


@router.post("/request-counselor")
def request_counselor(payload: CounselorRequest, user: dict = Depends(get_current_user)):
    require_session_owner(payload.session_id, user)
    try:
        existing = next((a for a in ALERTS if a["session_id"] == payload.session_id), None)
        if existing:
            existing["last_message"] = payload.message
            existing["timestamp"] = datetime.utcnow().isoformat() + "Z"
        else:
            alert_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "session_id": payload.session_id,
                "user_id": None,
                "intent": "student_requested",
                "anxiety_score": 0,
                "severity": "Requested",
                "message": payload.message,
                "last_message": payload.message,
                "status": "pending",
                "counselor_took_over": False,
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

            severity = meta.get("severity", "Normal")
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
                a["session_id"] == s["session_id"] and a["status"] == "pending"
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
                    "transcript": interactions.data,
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

        # Anxiety distribution from interactions
        interactions = supabase.table("interactions").select("severity").execute()
        severity_counts = {"Low": 0, "Moderate": 0, "High": 0, "Normal": 0}
        for row in interactions.data:
            s = row.get("severity", "Normal") or "Normal"
            if s in severity_counts:
                severity_counts[s] += 1

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
            "sessions_this_week": [{"day": d, "count": week_data[d]} for d in days],
            "total_sessions": len(supabase.table("sessions").select("id").execute().data),
            "total_alerts": len(alerts.data),
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
                .eq("session_id", session_id)
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
            messages.append(
                {
                    "sender": "user",
                    "text": row["message"],
                    "timestamp": row["timestamp"],
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
                        "timestamp": row["timestamp"],
                    }
                )

        user_id = session["student_id"]
        started_at = session["created_at"]

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
        summary_data = [
            ["Session ID", session_id],
            ["Started At", started_at],
            ["Total Messages", str(len(messages))],
            ["Peak Anxiety Level", str(meta.get("running_intent", "—")).title()],
            ["Final Confidence Score", f"{meta.get('running_confidence', 0):.0%}"],
            ["Resolved By", meta.get("resolved_by") or "Not yet resolved"],
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
