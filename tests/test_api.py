import os

import pytest

os.environ["SOPILOT_LAZY"] = "1"


@pytest.fixture(scope="module")
def client():
    from app import create_app
    return create_app().test_client()


def test_health(client):
    assert client.get("/api/health").get_json()["status"] == "ok"


def test_triage_validation(client):
    assert client.post("/api/triage", json={"text": ""}).status_code == 400
    assert client.post("/api/triage", json={"text": "x" * 6000}).status_code == 413
    assert client.post("/api/triage", json={"text": "hi", "policy": "yolo"}).status_code == 400


def test_triage_review_audit_flow(client):
    d = client.post("/api/triage", json={"text": "My Aero 15 battery is swelling and smoking", "policy": "frozen"}).get_json()
    assert d["action"] == "ESCALATE" and d["audit_id"]
    q = client.get("/api/queue").get_json()
    assert any(x["id"] == d["audit_id"] for x in q)
    assert client.post("/api/review", json={"decision_id": d["audit_id"], "reviewer": "t", "verdict": "edit"}).status_code == 400
    assert client.post("/api/review", json={"decision_id": d["audit_id"], "reviewer": "t", "verdict": "approve"}).status_code == 200
    log = client.get("/api/audit").get_json()
    assert log[0]["review"]["verdict"] == "approve"


def test_frozen_policy_never_automates(client):
    d = client.post("/api/triage", json={"text": "Where is my replacement battery? Order ORD-12345678", "policy": "frozen"}).get_json()
    assert d["automated"] is False
