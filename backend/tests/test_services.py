from fastapi.testclient import TestClient

from app.services.rule_intent import analyze_with_rules
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
