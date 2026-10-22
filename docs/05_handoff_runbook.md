# 5. Handoff and runbook

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd web && npm ci && npm run build && cd ..
python api/app.py                                     # http://localhost:5000
```

The app's Triage tab accepts typed tickets in live mode. `SOPILOT_AUDIT_DB=audit.db` keeps the audit log on disk; the default is in memory.

## Reproduce every number

```bash
export PYTHONPATH=src                        # Windows PowerShell: $env:PYTHONPATH="src"
python scripts/build_data.py                 # Pilot 1 data, KB, labeling guide, blind sheet
python -m sopilot.generate_v2 --out data/tickets   # Pilot 2 holdout data
python -m sopilot.train --pilot pilot1
python scripts/set_thresholds.py --pilot pilot1
python scripts/run_eval.py --pilot pilot1
python -m sopilot.train --pilot pilot2
python scripts/set_thresholds.py --pilot pilot2
python scripts/run_eval.py --pilot pilot2
python scripts/learning_curve.py
python scripts/make_figures.py
python scripts/build_web_data.py
pytest -q
```

Everything is seeded. The git history records the order: charter, data, models, frozen thresholds, then results.

## Deploy

**Vercel (frontend + serverless API).** From the repo root: `npx vercel deploy`. `vercel.json` builds `web/` and serves `api/index.py` as a Python function. `.vercelignore` keeps the bundle to the Pilot 2 artifacts (about 20 MB, mostly the 16 MB embedding matrix). The audit log lives in `/tmp` on serverless and resets on cold starts; use Render or a managed database for a durable log.

**Render (long-running API).** `render.yaml` runs `gunicorn` with a persistent disk for `audit.db`.

**Hosted read-only demo.** `cd web && npm run build:replay && cd .. && python scripts/build_artifact.py` produces `artifact/index.html`, which replays the pipeline's real decisions on held-out tickets and needs no server.

## Operating the policy

| Setting | Where | Current (Pilot 2 frozen) |
|---|---|---|
| Automation threshold | `outputs/pilot2/thresholds.json` → `auto_threshold` | 1.01 (off) |
| Critical threshold | `critical_threshold` | 0.03 |
| Multi-request detector | `multi_mode`, `multi_threshold` | cue, 0.85 |
| Sibling guard | `sibling_guard` | 0.10 |
| Non-English handling | `non_english` | allow |

Never edit a threshold by hand to raise coverage: rerun `set_thresholds.py` on fresh calibration data. A threshold the protocol did not certify is exploratory only (the app labels it so).

## Monitoring plan (if a later pilot goes live)

Monitor outcomes, not only inputs: input-drift statistics can stay flat while error rises.

| Signal | Source | Alert when |
|---|---|---|
| Reviewer override rate on automated replies (spot checks) | audit `reviews` table | > 3% weekly, or any override on a safety or legal topic |
| Escalation rate and escalation precision | audit + specialist disposition | precision < 40% or rate outside 2× the pilot baseline |
| Critical misses found after the fact | specialist feedback | any; each one is reviewed and added to the calibration set |
| Calibration (stated confidence vs reviewer agreement) | weekly sample of 200 decisions | ECE > 5 points |
| Intent mix vs calibration set | daily | an intent's share moves more than 2× |
| Language mix | daily | non-English share > 2× baseline |
| Injection detections | audit `reasons` | new phrasing patterns (add to the red-team set) |
| Latency p95 | API logs | > 500 ms |

## Rollback

1. Set `auto_threshold` above 1 (automation off). Every ticket then goes to people with drafts. This is a config change, not a deploy.
2. If routing suggestions themselves are suspect, turn the UI suggestion off and route by the existing manual process; the audit log keeps the history.
3. Record the incident, add the tickets to the calibration set, and rerun the threshold protocol before turning automation back on.

## Ownership

| Area | Owner (to assign) |
|---|---|
| Labeling guide and gold labels | Service operations process owner |
| Thresholds and the go/no-go protocol | Analytics / AI delivery |
| Safety, legal and privacy escalation lists | Trust & Safety, Legal, Privacy Office |
| Knowledge-base articles | Support content team |
| Monitoring and rollback | On-call analyst |
