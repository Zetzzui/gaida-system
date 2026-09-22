import json
from fastapi.testclient import TestClient

from app.services.rule_intent import analyze_with_rules
from app.services.virtual_agent import detect_intent_and_level, _build_result
from app.main import app


def test_rule_intent_basic():
    res = analyze_with_rules("I feel very anxious and nervous today")
    assert isinstance(res, dict)
    assert "intent" in res and "confidence" in res
    assert res["intent"] in ("anxiety", "neutral", "sadness", "stress", "other")
    assert 0.0 <= res["confidence"] <= 1.0


def test_virtual_agent_endpoint():
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={
            "student_number": "2024001",
            "email": "student1@ue.edu.ph",
            "access_code": "ACCESS123",
            "antibot": "HELLO",
        },
    )
    assert login.status_code == 200
    token = login.json()["session_token"]

    r = client.post(
        "/virtual-agent",
        json={"message": "I'm nervous and anxious", "user_id": "2024001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "intent" in data and "confidence" in data and "response" in data


def test_virtual_agent_requires_auth():
    client = TestClient(app)
    r = client.post("/virtual-agent", json={"message": "I'm nervous and anxious"})
    assert r.status_code == 401


def test_virtual_agent_stream():
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={
            "student_number": "2024001",
            "email": "student1@ue.edu.ph",
            "access_code": "ACCESS123",
            "antibot": "HELLO",
        },
    )
    assert login.status_code == 200
    token = login.json()["session_token"]

    r = client.post(
        "/virtual-agent/stream",
        json={"message": "I'm nervous and anxious"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")

    events = [json.loads(line) for line in r.text.strip().splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert types[0] == "delta"
    assert types[-1] == "done"

    streamed = "".join(e["text"] for e in events if e["type"] == "delta")
    assert streamed  # at least the fallback text arrived
    assert events[-1]["result"]["response"] == streamed


def test_virtual_agent_stream_requires_auth():
    client = TestClient(app)
    r = client.post("/virtual-agent/stream", json={"message": "hello"})
    assert r.status_code == 401


# ---- Tier 1: Detection accuracy guards ------------------------------------


def test_safe_phrase_does_not_mask_real_crisis():
    """A real suicidal phrase combined with a safe venting phrase must still
    trigger crisis, not be neutralised by the safe-phrase whitelist."""
    r = detect_intent_and_level("ayoko na mag aral, gusto ko na mamatay")
    assert r["anxiety_level"] == "Crisis", f"got {r['anxiety_level']}"


def test_school_venting_downgraded_to_stress():
    """A soft give-up phrase in a school/work context is stress, not suicidal."""
    r = analyze_with_rules("hindi ko na kaya ang requirements at deadlines, ayoko na ng lahat")
    assert r["intent"] in ("stress", "sadness"), f"got {r['intent']}"
    assert r["confidence"] <= 0.99, "should not be hard-escalated"


def test_real_crisis_always_crisis():
    """Explicit self-harm language with no fiction/venting context."""
    r = detect_intent_and_level("i want to kill myself tonight")
    assert r["anxiety_level"] == "Crisis"


def test_anger_capped_below_high():
    """Anger should never reach 'high' or 'Crisis' severity."""
    r = _build_result("anger", 0.99)
    assert r["anxiety_level"] == "low", f"got {r['anxiety_level']}"
    assert r["anxiety_score"] == 1


def test_hypothetical_suicidal_kept_at_high_not_crisis():
    """Hypothetical hedged ideation still alerts (high) but avoids full crisis."""
    r = detect_intent_and_level("what if i kill myself, does anyone care")
    assert r["intent"] == "suicidal"
    assert r["anxiety_level"] == "high"
    assert r["confidence"] < 0.99


def test_crisis_hold_requires_safety_confirmation():
    """The de-escalation clearance hold: after a crisis turn, a neutral
    greeting must NOT silently drop the session below High/Crisis while the
    student hasn't explicitly confirmed they're safe. An explicit safety
    confirmation clears the hold so a later calm message can de-escalate."""
    from app.services.intent_router import _prepare_turn
    from app.services.session_manager import get_session

    crisis = _prepare_turn("Ayoko na mabuhay, gusto ko nang mamatay", "SESS_TEST_GREET", "u1")
    assert crisis["severity"] == "Crisis"

    # Hold: a neutral greeting keeps the escalated reading (no silent drop).
    greeting = _prepare_turn("hello", "SESS_TEST_GREET", "u1")
    assert greeting["severity"] in ("High", "Crisis"), f"got {greeting['severity']}"

    # Explicit safety confirmation clears the hold flag…
    confirmed = _prepare_turn("safe na ako", "SESS_TEST_GREET", "u1")
    session = get_session("SESS_TEST_GREET")
    assert session["meta"].get("needs_clearance") is False

    # …so a calm closing message can then de-escalate below High.
    calm = _prepare_turn("okay salamat", "SESS_TEST_GREET", "u1")
    assert calm["severity"] not in ("High", "Crisis"), f"got {calm['severity']}"


# ---- Tier 2: Escalation deadlines (server side) -----------------------------


def test_escalation_deadline_flags_overdue_and_notifies():
    """A pending, unacknowledged Crisis alert far past the deadline must be
    marked overdue, flagged needs_supervisor, and a re-notification must be
    logged — so an unattended crisis can't silently sit in the dashboard."""
    from datetime import datetime, timezone, timedelta

    from app.api.counselor import ALERTS, run_escalation_checks

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=120)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    alert = {
        "timestamp": old_ts,
        "session_id": "SESS_ESC_OVERDUE",
        "intent": "suicidal",
        "severity": "Crisis",
        "status": "pending",
        "acknowledged": False,
        "message": "i want to die",
        "last_message": "i want to die",
        "anxiety_score": 5,
    }
    saved = list(ALERTS)
    ALERTS[:] = []
    try:
        ALERTS.append(alert)
        res = run_escalation_checks()

        assert alert["escalation_level"] == "overdue", alert["escalation_level"]
        assert alert["needs_supervisor"] is True
        assert res["overdue"] == 1
        # A re-notification attempt was made and audit-logged
        assert len(alert.get("notifications", [])) >= 1
        assert alert["notifications"][-1]["level"] == "overdue"
        assert alert["notifications"][-1]["channel"] == "email"
    finally:
        ALERTS[:] = saved


def test_fresh_alert_not_escalated():
    """A brand-new pending alert must stay at normal level with no re-notify
    and no supervisor flag."""
    from datetime import datetime, timezone

    from app.api.counselor import ALERTS, run_escalation_checks

    fresh = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "session_id": "SESS_ESC_FRESH",
        "intent": "anxiety",
        "severity": "High",
        "status": "pending",
        "acknowledged": False,
        "message": "i cant take this anymore",
        "last_message": "i cant take this anymore",
        "anxiety_score": 5,
    }
    saved = list(ALERTS)
    ALERTS[:] = []
    try:
        ALERTS.append(fresh)
        run_escalation_checks()
        assert fresh["escalation_level"] == "normal"
        assert fresh.get("needs_supervisor") is not True
        assert fresh.get("notifications") in (None, [])
    finally:
        ALERTS[:] = saved


def test_escalation_reset_for_acknowledged_alert():
    """An acknowledged alert (already seen by a human) must drop back to
    normal and never be re-notified."""
    from datetime import datetime, timezone, timedelta

    from app.api.counselor import ALERTS, run_escalation_checks

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    ack = {
        "timestamp": old_ts,
        "session_id": "SESS_ESC_ACK",
        "intent": "suicidal",
        "severity": "Crisis",
        "status": "pending",
        "acknowledged": True,
        "message": "i want to die",
        "last_message": "i want to die",
        "anxiety_score": 5,
        "escalation_level": "overdue",
        "needs_supervisor": True,
    }
    saved = list(ALERTS)
    ALERTS[:] = []
    try:
        ALERTS.append(ack)
        run_escalation_checks()
        assert ack["escalation_level"] == "normal"
        assert ack["needs_supervisor"] is False
        assert ack.get("notifications") in (None, [])
    finally:
        ALERTS[:] = saved


def test_welfare_check_flags_silent_high_session():
    """A High/Crisis session silent past the threshold must be flagged for a
    welfare check. Previously the naive-vs-aware datetime math raised TypeError
    and silently skipped every in-memory session."""
    import uuid
    from datetime import datetime, timezone, timedelta

    from app.services.session_manager import (
        SESSIONS,
        get_sessions_needing_welfare_check,
    )

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    sid = "SESS_WELFARE_" + uuid.uuid4().hex[:8]
    SESSIONS[sid] = {
        "session_id": sid,
        "user_id": "u1",
        "active": True,
        "started_at": old_ts,
        "messages": [{"sender": "user", "text": "i want to die", "timestamp": old_ts}],
        "meta": {"peak_severity": "Crisis", "counselor_active": False},
    }
    try:
        flagged = get_sessions_needing_welfare_check(stale_minutes=30)
        matches = [f for f in flagged if f["session_id"] == sid]
        assert matches, "silent Crisis session was not flagged for welfare check"
        assert matches[0]["peak_severity"] == "Crisis"
        assert matches[0]["idle_minutes"] >= 30
    finally:
        SESSIONS.pop(sid, None)
