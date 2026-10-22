"""Append-only audit log (SQLite). Decisions are never updated in place;
reviewer actions are separate rows that reference a decision."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY, ts REAL NOT NULL, ticket_ref TEXT, redacted_text TEXT NOT NULL,
  intent TEXT, queue TEXT, action TEXT NOT NULL, confidence REAL, reasons TEXT, payload TEXT,
  model_version TEXT, policy_version TEXT, latency_ms REAL
);
CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY, ts REAL NOT NULL, decision_id TEXT NOT NULL REFERENCES decisions(id),
  reviewer TEXT NOT NULL, verdict TEXT NOT NULL CHECK (verdict IN ('approve','edit','reject')),
  final_text TEXT, note TEXT
);
CREATE TRIGGER IF NOT EXISTS no_update_decisions BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_decisions BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


class AuditLog:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    def record(self, decision: dict, ticket_ref: str | None = None) -> str:
        did = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, time.time(), ticket_ref, decision["redacted_text"], decision.get("intent"), decision.get("queue"),
             decision["action"], decision.get("confidence"), json.dumps(decision.get("reasons", [])),
             json.dumps(decision), decision.get("model_version"), decision.get("policy_version"), decision.get("latency_ms")))
        self.db.commit()
        return did

    def review(self, decision_id: str, reviewer: str, verdict: str, final_text: str | None = None, note: str = "") -> str:
        if not self.db.execute("SELECT 1 FROM decisions WHERE id=?", (decision_id,)).fetchone():
            raise KeyError(decision_id)
        rid = str(uuid.uuid4())
        self.db.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
                        (rid, time.time(), decision_id, reviewer, verdict, final_text, note))
        self.db.commit()
        return rid

    def pending(self, limit: int = 50):
        rows = self.db.execute(
            """SELECT d.id, d.ts, d.intent, d.queue, d.action, d.confidence, d.payload FROM decisions d
               LEFT JOIN reviews r ON r.decision_id = d.id
               WHERE r.id IS NULL AND d.action IN ('HUMAN_REVIEW','ESCALATE')
               ORDER BY CASE d.action WHEN 'ESCALATE' THEN 0 ELSE 1 END, d.ts DESC LIMIT ?""", (limit,)).fetchall()
        return [{"id": r[0], "ts": r[1], "intent": r[2], "queue": r[3], "action": r[4], "confidence": r[5],
                 "decision": json.loads(r[6])} for r in rows]

    def entries(self, limit: int = 100):
        rows = self.db.execute(
            """SELECT d.id, d.ts, d.action, d.intent, d.confidence, d.reasons, d.model_version, d.policy_version,
                      r.verdict, r.reviewer, r.ts FROM decisions d LEFT JOIN reviews r ON r.decision_id = d.id
               ORDER BY d.ts DESC LIMIT ?""", (limit,)).fetchall()
        return [{"id": r[0], "ts": r[1], "action": r[2], "intent": r[3], "confidence": r[4], "reasons": json.loads(r[5]),
                 "model_version": r[6], "policy_version": r[7], "review": ({"verdict": r[8], "reviewer": r[9], "ts": r[10]} if r[8] else None)}
                for r in rows]
