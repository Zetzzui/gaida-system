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
