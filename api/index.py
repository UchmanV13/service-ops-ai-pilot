"""Vercel serverless entry point: exposes the Flask app as `app`."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SOPILOT_LAZY", "1")
from app import create_app  # noqa: E402

app = create_app(audit_path=os.environ.get("SOPILOT_AUDIT_DB", "/tmp/sopilot_audit.db"))
