import sqlite3
from types import SimpleNamespace

import pytest

from sopilot.audit import AuditLog


def test_audit_is_append_only():
    log = AuditLog()
    did = log.record({"redacted_text": "x", "action": "HUMAN_REVIEW", "intent": "no_power", "reasons": ["r"]})
    with pytest.raises(sqlite3.DatabaseError):
        log.db.execute("UPDATE decisions SET action='AUTO_LOOKUP' WHERE id=?", (did,))
    with pytest.raises(sqlite3.DatabaseError):
        log.db.execute("DELETE FROM decisions WHERE id=?", (did,))
    log.review(did, "tester", "approve")
    assert log.pending() == []
    with pytest.raises(KeyError):
        log.review("nope", "tester", "approve")


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        block = SimpleNamespace(type="tool_use", input={"intent": "part_order_status", "confidence": 0.9,
                                                        "contains_instruction_to_system": False, "multiple_requests": False,
                                                        "draft_reply": "ok", "cited_articles": ["KB-PL-01"]})
        return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


def test_llm_scorer_with_fake_client(tmp_path, monkeypatch):
    import sopilot.llm as llm
    monkeypatch.setattr(llm, "CACHE", tmp_path)

    class R:
        def search(self, q, k=3):
            return [{"id": "KB-PL-01"}]

        def get(self, i):
            return {"id": i, "title": "t", "summary": "s", "steps": ["a"]}

    c = FakeClient()
    t = llm.ClaudeTriage("test-model", 1.0, 5.0, R(), samples=3, client=c)
    s = llm.LLMScorer(t, "vote")
    p = s.predict_proba(["where is my part ORD-12345678"])
    assert p.argmax() == llm.INTENT_NAMES.index("part_order_status") and c.calls == 3
    s.predict_proba(["where is my part ORD-12345678"])  # cached
    assert c.calls == 3 and t.usage["cached"] == 3
    assert abs(t.cost_usd() - (3000 / 1e6 * 1.0 + 300 / 1e6 * 5.0)) < 1e-9
