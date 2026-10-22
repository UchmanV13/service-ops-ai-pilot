"""Flask API for the Service Operations AI Pilot (Halden Devices, fictional).

    pip install -r requirements.txt
    python api/app.py            # http://localhost:5000

Endpoints
  GET  /api/health
  GET  /api/policies             frozen pilot policy and the exploratory policy
  POST /api/triage               {"text": "...", "policy": "frozen"|"exploratory"}
  GET  /api/queue                decisions waiting for a person
  POST /api/review               {"decision_id", "reviewer", "verdict": approve|edit|reject, "final_text"}
  GET  /api/audit                recent decisions and reviews (append-only log)
  GET  /api/results              evaluation summary for the dashboard
  GET  /api/samples              held-out sample tickets for the demo
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sopilot.audit import AuditLog  # noqa: E402
from sopilot.pipeline import Params, Pipeline  # noqa: E402

PILOT = os.environ.get("SOPILOT_PILOT", "pilot2")
MAX_CHARS = 5000


def load_policies():
    th = json.loads((ROOT / "outputs" / PILOT / "thresholds.json").read_text())
    p = th["arms"]["ensemble"]["params"]
    frozen = Params(**{k: v for k, v in p.items() if k in Params.__dataclass_fields__})
    exploratory = replace(frozen, auto_threshold=0.95, version=f"{PILOT}-exploratory-0.95")
    return {"frozen": frozen, "exploratory": exploratory}


def create_app(audit_path: str | None = None, pipeline: Pipeline | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(ROOT / "web" / "dist"), static_url_path="")
    pipe = pipeline or Pipeline.load(art=ROOT / "artifacts" / PILOT)
    policies = load_policies()
    audit = AuditLog(audit_path or os.environ.get("SOPILOT_AUDIT_DB", ":memory:"))
    replay = ROOT / "web" / "public" / "replay.json"

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("CORS_ORIGINS", "*")
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return resp

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", pilot=PILOT, model=pipe.model_version)

    @app.get("/api/policies")
    def get_policies():
        return jsonify({k: asdict(v) | {"certified": k == "frozen"} for k, v in policies.items()})

    @app.post("/api/triage")
    def triage():
        body = request.get_json(silent=True) or {}
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="'text' must be a non-empty string"), 400
        if len(text) > MAX_CHARS:
            return jsonify(error=f"ticket text is limited to {MAX_CHARS} characters"), 413
        policy = body.get("policy", "frozen")
        if policy not in policies:
            return jsonify(error=f"policy must be one of {sorted(policies)}"), 400
        d = pipe.triage(text, policies[policy], audit=audit, ticket_ref=body.get("ref"))
        return jsonify(d)

    @app.get("/api/queue")
    def queue():
        return jsonify(audit.pending(int(request.args.get("limit", 50))))

    @app.post("/api/review")
    def review():
        b = request.get_json(silent=True) or {}
        if b.get("verdict") not in ("approve", "edit", "reject"):
            return jsonify(error="verdict must be approve, edit or reject"), 400
        if not b.get("reviewer"):
            return jsonify(error="reviewer is required"), 400
        if b["verdict"] == "edit" and not b.get("final_text"):
            return jsonify(error="final_text is required for an edit"), 400
        try:
            rid = audit.review(b.get("decision_id", ""), b["reviewer"], b["verdict"], b.get("final_text"), b.get("note", ""))
        except KeyError:
            return jsonify(error="unknown decision_id"), 404
        return jsonify(review_id=rid)

    @app.get("/api/audit")
    def audit_log():
        return jsonify(audit.entries(int(request.args.get("limit", 100))))

    @app.get("/api/results")
    def results():
        f = ROOT / "web" / "public" / "results_summary.json"
        return (f.read_text(), 200, {"Content-Type": "application/json"}) if f.exists() else (jsonify(error="run scripts/build_web_data.py"), 404)

    @app.get("/api/samples")
    def samples():
        if not replay.exists():
            return jsonify([])
        return jsonify([{"id": t["id"], "label": t["label"], "text": t["text"]} for t in json.loads(replay.read_text())["tickets"]])

    @app.get("/")
    def index():
        dist = ROOT / "web" / "dist"
        return send_from_directory(dist, "index.html") if (dist / "index.html").exists() else ("API running. Build the web app with `npm run build` in web/.", 200)

    return app


app = create_app() if os.environ.get("SOPILOT_LAZY") != "1" else None

if __name__ == "__main__":
    (app or create_app()).run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
