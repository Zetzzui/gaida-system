from typing import Dict, Any, List, Callable
from datetime import datetime, timezone, timedelta
import uuid
from app.database.database import supabase
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.utils.consent_checker import has_consent

SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_STALE_MINUTES = 30  # sessions with no activity in this window are excluded from "active"
WELFARE_CHECK_MINUTES = 30  # a High/Crisis session silent for this long is flagged for welfare check
_SUBSCRIBERS: List[Callable] = []

# Welfare-check DB fallback throttle (the dashboard polls this endpoint).
_WELFARE_DB_LAST_SCAN = datetime.fromtimestamp(0, tz=timezone.utc)
_WELFARE_DB_SCAN_MIN = timedelta(minutes=1)

# Single worker so DB/file writes never block the chat response AND are
# serialized (avoids swallowing writes from concurrent messages).
_PERSIST_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gaida-persist")

# The server's main asyncio event loop, captured on the first WebSocket
# connection (WebSocket handlers always run on the server loop). Sync FastAPI
# endpoints execute in worker threads where there is no running loop, so
# `asyncio.create_task(...)` there raises and would silently drop broadcasts —
# the thread-safe scheduler below routes through this loop instead.
_MAIN_LOOP = None


def set_main_loop(loop):
    """Remember the running server event loop (called by the session WS handler)."""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _schedule_coro(coro):
    """Run an async callback on the live server loop from any context.

    Prefers the calling thread's running loop (async endpoints); falls back to
    the captured main loop via call_soon_threadsafe when called from a worker
    thread. If no loop is available there are no WebSocket clients to deliver
    to, so the coroutine is simply closed instead of leaking.
    """
    try:
        asyncio.get_running_loop()
        asyncio.create_task(coro)
        return
    except RuntimeError:
        pass
    loop = _MAIN_LOOP
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro))
    else:
        coro.close()


def load_session_from_db(session_id: str) -> Dict[str, Any] | None:
    """Rehydrate a session (messages + meta) from Supabase so returning
    students resume the exact conversation they had before.

    Returns None if no interactions exist for this session.

    The sessions row is also read so a backend restart can't resurrect an
    explicitly ended (ended_at set) or resolved session as "active": those
    come back inactive/resolved instead of showing up as live chats again.
    """
    try:
        rows = (
            supabase.table("interactions")
            .select("*")
            .eq("session_id", session_id)
            .order("timestamp")
            .execute()
        )
    except Exception as e:
        print(f"Session load error: {e}")
        return None

    data = rows.data
    if not data:
        return None

    # End/resolve state lives on the sessions row (never inside interactions).
    # Defaults keep working even if the row/columns are missing.
    ended_at = None
    resolved = False
    resolved_at = None
    resolved_by = None
    # Counselor-takeover state also lives on the sessions row. `None` means the
    # columns don't exist yet (legacy rows) → fall back to the alerts table.
    counselor_active = None
    assigned_counselor_id = None
    try:
        sess_rows = (
            supabase.table("sessions")
            .select("ended_at, resolved, resolved_at, resolved_by, counselor_active, assigned_counselor_id")
            .eq("session_token", session_id)
            .limit(1)
            .execute()
        ).data
        if sess_rows:
            row0 = sess_rows[0]
            ended_at = row0.get("ended_at")
            resolved = bool(row0.get("resolved"))
            resolved_at = row0.get("resolved_at")
            resolved_by = row0.get("resolved_by")
            counselor_active = row0.get("counselor_active")
            assigned_counselor_id = row0.get("assigned_counselor_id")
    except Exception as e:
        print(f"Session load error (sessions row): {e}")

    # Legacy rows (created before the takeover columns existed) have no
    # counselor_active value — restore it from counselor_alerts instead: a row
    # marked status=escalated + counselor_took_over means a counselor took over
    # and never handed the session back. Without this, a restart silently
    # flips the conversation back to GAIDA/student on both dashboards.
    if counselor_active is None:
        try:
            alert_rows = (
                supabase.table("counselor_alerts")
                .select("status, counselor_took_over")
                .eq("session_id", session_id)
                .eq("status", "escalated")
                .limit(1)
                .execute()
            ).data or []
            if alert_rows and bool(alert_rows[0].get("counselor_took_over")):
                counselor_active = True
        except Exception as e:
            print(f"Session load error (counselor_alerts fallback): {e}")
    counselor_active = bool(counselor_active)

    # Each row is one user turn + GAIDA's reply (stored in `response`).
    # Counselor takeover messages and system notices are rows with no GAIDA
    # reply; the alerts-transcript logic distinguishes them by intent:
    # counselor_intervention = a counselor, intent None = a system notice,
    # anything else = a user turn (with GAIDA's reply if present). Label the
    # rehydrated messages the same way so both dashboards render and flag the
    # conversation correctly after a restart.
    messages = []
    for row in data:
        ts = row.get("timestamp")
        msg = row.get("message", "")
        intent = row.get("intent")
        if intent == "counselor_intervention":
            messages.append({"sender": "counselor", "text": msg, "timestamp": ts})
        elif intent is None and msg:
            messages.append({"sender": "system", "text": msg, "timestamp": ts})
        else:
            messages.append({"sender": "user", "text": msg, "timestamp": ts})
            if row.get("response"):
                messages.append({"sender": "bot", "text": row["response"], "timestamp": ts})

    last = data[-1]

    # Recompute peak severity from the full history (sessions table is stale mid-session).
    SEVERITY_RANK = {"Normal": 0, "Low": 1, "Moderate": 2, "High": 3, "Crisis": 4}
    peak_severity = "Normal"
    peak_confidence = 0.3
    for row in data:
        sev = row.get("severity") or "Normal"
        try:
            conf = float(row["confidence"]) if row.get("confidence") is not None else 0.0
        except (TypeError, ValueError):
            conf = 0.0
        if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(peak_severity, 0):
            peak_severity = sev
            peak_confidence = conf

    # Rebuild the anti-repetition theme list (same rule as intent_router Step 9b).
    covered_themes = []
    for row in data:
        resp = row.get("response")
        if not resp:
            continue
        sentences = [s.strip() for s in resp.split('.') if s.strip()]
        if sentences:
            covered_themes.append(sentences[-1])
    covered_themes = covered_themes[-5:]

    try:
        last_confidence = float(last["confidence"]) if last.get("confidence") is not None else 0.3
    except (TypeError, ValueError):
        last_confidence = 0.3

    meta = {
        "running_intent": last.get("intent") or "neutral",
        "running_confidence": last_confidence,
        "intensity": last.get("anxiety_score"),
        "peak_severity": peak_severity,
        "peak_confidence": peak_confidence,
        "post_crisis": last.get("intent") == "suicidal" or last.get("severity") in ("High", "Crisis"),
        "pending_acoustic": None,
        "covered_themes": covered_themes,
        "resolved": resolved,
        "resolved_at": resolved_at,
        "resolved_by": resolved_by,
        # Restored counselor-held state so a rehydrated session stays on the
        # counselor side (see takeover fallback above).
        "counselor_active": counselor_active,
        "assigned_counselor_id": assigned_counselor_id,
    }

    return {
        "session_id": session_id,
        "user_id": last.get("student_id") or None,
        "messages": messages,
        "active": not bool(ended_at),
        "ended_at": ended_at,
        "meta": meta,
        "started_at": messages[0]["timestamp"] if messages else None,
    }


def start_session(user_id: str | None = None, session_id: str | None = None) -> str:
    sid = session_id or str(uuid.uuid4())
    if sid in SESSIONS:
        return sid

    # Returning student — rehydrate their previous conversation before
    # creating a blank session (only when a session_id was supplied).
    if session_id:
        restored = load_session_from_db(sid)
        if restored:
            if user_id:
                restored["user_id"] = user_id
            SESSIONS[sid] = restored
            return sid

    SESSIONS[sid] = {
        "session_id": sid,
        "user_id": user_id,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "messages": [],
        "active": True,
        "meta": {
            "running_confidence": 0.3,
            "running_intent": "neutral",
            "peak_severity": "Normal",
            "peak_confidence": 0.3,
        }
    }
    try:
        from app.database.database import supabase
        supabase.table("sessions").insert({
            "session_token": sid,
            "student_id": user_id,
            "peak_severity": "Normal",
            "started_at": SESSIONS[sid]["started_at"],
        }).execute()
    except Exception as e:
        print(f"Session insert error: {e}")
    return sid


def subscribe(callback: Callable):
    """Register a callback to be invoked on new interactions.

    Callback signature: callback(session_id: str, entry: dict)
    Supports sync or async callables.
    """
    _SUBSCRIBERS.append(callback)


def _notify_subscribers(session_id: str, entry: Dict[str, Any]):
    for cb in list(_SUBSCRIBERS):
        try:
            if asyncio.iscoroutinefunction(cb):
                # Route through the scheduler: record_interaction() is called
                # from both async endpoints (event-loop context) and sync
                # endpoints running in FastAPI worker threads.
                _schedule_coro(cb(session_id, entry))
            else:
                cb(session_id, entry)
        except Exception:
            # swallow subscriber errors to avoid breaking main flow
            pass


def publish_event(session_id: str, payload: Dict[str, Any]):
    """Push an ad-hoc realtime event (typing, takeover, hand-back, ...) to a
    session's subscribers — currently the per-session WebSocket manager in
    app/api/session.py. Safe to call from sync or async endpoints."""
    _notify_subscribers(session_id, payload)


def _resolve_student_id(session_id: str) -> str | None:
    s = SESSIONS.get(session_id)
    return s.get("user_id") if s else None

def _persist_entry(entry: Dict[str, Any]):
    if entry.get("sender") == "bot":
        return
    try:
        analysis = entry.get("analysis", {}) or {}
        session_id = entry.get("session_id", "")
        supabase.table("interactions").insert({
            "session_id": session_id,
            "student_id": _resolve_student_id(session_id) or session_id,
            "message": entry.get("text"),
            "response": entry.get("response") or "",
            "timestamp": entry.get("timestamp"),
            "intent": str(analysis.get("intent", "")) if analysis.get("intent") else None,
            "confidence": float(analysis.get("confidence", 0)) if analysis.get("confidence") else None,
            "anxiety_score": analysis.get("intensity"),
            "severity": analysis.get("severity"),
            "method": "gpt",
        }).execute()
    except Exception as e:
        print(f"Supabase insert error: {e}")


def _persist_session_data(session_id: str, entry: Dict[str, Any]):
    """Runs in the background executor — consent check, Supabase insert,
    and log file write must never block the chat response."""
    try:
        if not has_consent(session_id):
            return

        _persist_entry(entry)

        from app.utils.logger import log_interaction

        if entry.get("sender") == "user":
            log_interaction(
                session_id=session_id,
                user_message=entry.get("text", ""),
                intent=entry.get("analysis", {}).get("intent", "unknown"),
                confidence=entry.get("analysis", {}).get("confidence", 0.0),
                anxiety_score=entry.get("analysis", {}).get("intensity", 0),
                response=entry.get("response") or "",
                method="session-manager",
            )
        else:
            log_interaction(
                session_id=session_id,
                user_message=entry.get("text", ""),
                intent=entry.get("analysis", {}).get("intent", ""),
                confidence=entry.get("analysis", {}).get("confidence", 0.0),
                anxiety_score=entry.get("analysis", {}).get("anxiety_score", 0),
                response=entry.get("response") or "",
                method="session-manager",
            )
    except Exception:
        pass


def record_interaction(session_id: str, sender: str, text: str, analysis: Dict | None = None, response: str | None = None):
    session = SESSIONS.get(session_id)
    if session is None:
        # create ephemeral session if missing
        session_id = start_session(None)
        session = SESSIONS[session_id]

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "sender": sender,
        "text": text,
        "analysis": analysis or {},
        "response": response,
    }
    session["messages"].append(entry)

    # A student sending a message means the session is live again — a student
    # who refreshed/left mid-chat (pagehide end beacon) but keeps talking must
    # not stay hidden as "ended". Re-activating also clears ended_at in
    # Supabase so a later restart rehydrates it as active. Counselor/system
    # writes never resurrect a closed session.
    if sender == "user" and not session.get("active"):
        session["active"] = True
        if session.get("ended_at"):
            session["ended_at"] = None
            try:
                supabase.table("sessions").update({"ended_at": None}).eq(
                    "session_token", session_id
                ).execute()
            except Exception as e:
                print(f"Session resume update error: {e}")

    # Update session-level meta (last intent, confidence, intensity, escalate)
    if analysis:
        session["meta"]["last_intent"] = analysis.get("intent")
        session["meta"]["confidence"] = analysis.get("confidence")
        session["meta"]["intensity"] = analysis.get("intensity")
        if analysis.get("escalate"):
            session["meta"]["escalate"] = True

        
        SEVERITY_RANK = {"Normal": 0, "Low": 1, "Moderate": 2, "High": 3, "Crisis": 4}
        new_severity = analysis.get("severity", "Normal")
        new_confidence = analysis.get("confidence", 0.0) or 0.0
        current_peak = session["meta"].get("peak_severity", "Normal")
        if SEVERITY_RANK.get(new_severity, 0) > SEVERITY_RANK.get(current_peak, 0):
            session["meta"]["peak_severity"] = new_severity
            session["meta"]["peak_confidence"] = new_confidence

    # Persist only if consent exists — offloaded to a background thread so
    # Supabase/file writes never block the chat response.
    try:
        _PERSIST_EXECUTOR.submit(_persist_session_data, session_id, entry)
    except Exception:
        pass

    _notify_subscribers(session_id, entry)


def get_session(session_id: str):
    s = SESSIONS.get(session_id)
    if s is None:
        # Safety net: fall back to Supabase so counselors/guards see history too.
        s = load_session_from_db(session_id)
        if s:
            SESSIONS[session_id] = s
    return s


def list_active_sessions():
    now = datetime.now(timezone.utc)
    result = []
    for s in SESSIONS.values():
        if not s.get("active"):
            continue
        if len(s.get("messages", [])) == 0:
            continue  # never sent a message — likely a stray/incomplete session
        last_msg_time = s["messages"][-1].get("timestamp")
        if last_msg_time:
            try:
                # Sessions rehydrated from Supabase carry aware "+00:00"
                # timestamps; in-memory ones use trailing "Z". Parsing both
                # to aware UTC keeps the 30-min idle filter actually running
                # (a naive-vs-aware subtraction raised TypeError before and
                # every session was silently kept "active" forever).
                last_dt = _parse_utc_aware(last_msg_time)
                age_minutes = (now - last_dt).total_seconds() / 60
                if age_minutes > SESSION_STALE_MINUTES:
                    continue  # no activity in 30+ minutes — treat as abandoned
            except (ValueError, TypeError):
                pass
        result.append(s)
    return result

def _parse_utc_aware(value):
    """Parse any stored timestamp to a timezone-aware UTC datetime. Naive values
    are treated as UTC. (The old code subtracted a naive `now` from an aware
    parsed timestamp, which raised TypeError and silently skipped every session.)"""
    if isinstance(value, datetime):
        dt = value
    else:
        import re as _re

        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00" if not _re.search(r"[+-]\d{2}:?\d{2}$", s[:-1]) else s[:-1]
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_sessions_needing_welfare_check(stale_minutes: int = WELFARE_CHECK_MINUTES) -> List[Dict[str, Any]]:
    """At-risk students who went silent: sessions whose peak severity reached
    High/Crisis and have had no activity for `stale_minutes` or more.
    Surfaces these to a counselor so a human welfare check happens instead of
    simply hiding the session as "abandoned" (which is all SESSION_STALE_MINUTES
    did before).

    The live scan only sees sessions still in memory, so a DB fallback
    re-flags High/Crisis sessions from Supabase that aren't in memory (e.g.
    after a backend restart) — a silent at-risk student is never lost."""
    now = datetime.now(timezone.utc)
    flagged: List[Dict[str, Any]] = []
    seen: set = set()

    # ── Live (in-memory) scan ──────────────────────────────────────────────
    for sid, s in SESSIONS.items():
        if not s.get("active"):
            continue
        severity = s.get("meta", {}).get("peak_severity", "Normal")
        if severity not in ("High", "Crisis"):
            continue
        if s.get("meta", {}).get("counselor_active"):
            continue
        last_ts = None
        if s.get("messages"):
            last_ts = s["messages"][-1].get("timestamp")
        if not last_ts:
            last_ts = s.get("started_at")
        if not last_ts:
            continue
        try:
            last_dt = _parse_utc_aware(last_ts)
        except (ValueError, TypeError):
            continue
        idle_minutes = (now - last_dt).total_seconds() / 60
        if idle_minutes >= stale_minutes:
            flagged.append({
                "session_id": sid,
                "student_id": s.get("user_id"),
                "peak_severity": severity,
                "idle_minutes": round(idle_minutes),
                "last_message": (s["messages"][-1].get("text", "") if s.get("messages") else ""),
            })
            seen.add(sid)

    # ── DB fallback (sessions not in memory, e.g. after restart) ───────────
    # Throttled so the dashboard's polling doesn't hammer Supabase.
    global _WELFARE_DB_LAST_SCAN
    if now - _WELFARE_DB_LAST_SCAN < _WELFARE_DB_SCAN_MIN:
        return flagged
    _WELFARE_DB_LAST_SCAN = now

    try:
        from app.database.database import supabase

        rows = (
            supabase.table("sessions")
            .select("session_token, student_id, peak_severity, created_at")
            .in_("peak_severity", ["High", "Crisis"])
            .is_("ended_at", "null")
            .execute()
        ).data or []
        for row in rows:
            sid = row.get("session_token")
            if not sid or sid in seen or sid in SESSIONS:
                continue
            sev = row.get("peak_severity") or "High"
            last_msg = ""
            last_ts = row.get("created_at")
            try:
                last_rows = (
                    supabase.table("interactions")
                    .select("timestamp, message")
                    .eq("session_id", sid)
                    .order("timestamp", desc=True)
                    .limit(1)
                    .execute()
                ).data or []
                if last_rows:
                    last_ts = last_rows[0].get("timestamp") or last_ts
                    last_msg = last_rows[0].get("message") or last_msg
            except Exception:
                last_msg = ""
            if not last_ts:
                continue
            try:
                last_dt = _parse_utc_aware(last_ts)
            except (ValueError, TypeError):
                continue
            idle_minutes = (now - last_dt).total_seconds() / 60
            if idle_minutes >= stale_minutes:
                flagged.append({
                    "session_id": sid,
                    "student_id": row.get("student_id"),
                    "peak_severity": sev,
                    "idle_minutes": round(idle_minutes),
                    "last_message": last_msg,
                    "from_db": True,
                })
                seen.add(sid)
    except Exception as e:
        print(f"Welfare DB fallback error: {e}")

    return flagged

def end_session(session_id: str):
    s = SESSIONS.get(session_id)
    if s:
        s["active"] = False
        s["ended_at"] = datetime.utcnow().isoformat() + "Z"
        peak = s["meta"].get("peak_severity", "Normal")
        student_id = s.get("user_id")
        try:
            from app.database.database import supabase
            result = supabase.table("sessions").update({
                "ended_at": s["ended_at"],
                "peak_severity": peak,
                "student_id": student_id,
            }).eq("session_token", session_id).execute()
        except Exception as e:
            print(f"Session end update error: {e}")