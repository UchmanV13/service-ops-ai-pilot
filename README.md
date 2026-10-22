# Service Operations AI Pilot

An end-to-end AI delivery engagement for a fictional hardware vendor's service desk (*Halden Devices*). It runs from opportunity assessment to a working triage system to two pre-registered pilots and a deployment decision.

> **Result:** both pilots came back **NO-GO** on criteria fixed before testing. The system routes 89% of unseen tickets correctly and catches 97.5% of safety, security, legal and outage cases. Catching them costs more in false escalations than automation saves, so the recommendation is a third pilot on real data, not deployment. See [`docs/04_pilot_readout.md`](docs/04_pilot_readout.md).

*All tickets are synthetic or hand-written and the company does not exist. Cost inputs are illustrative.*

## What's here

| Stage | Artifact |
|---|---|
| Discover and prioritize | [`docs/01_opportunity_assessment.md`](docs/01_opportunity_assessment.md): six candidate automations scored, one rejected |
| Pre-register | [`docs/02_pilot_charter.md`](docs/02_pilot_charter.md), [`docs/02b_pilot2_charter.md`](docs/02b_pilot2_charter.md): go/no-go criteria, threshold protocol, change log |
| Label | [`docs/03_labeling_guide.md`](docs/03_labeling_guide.md) (generated from the taxonomy), blind sheet + kappa script for a human agreement check |
| Build | `src/sopilot/`: guards, extraction, scorers, retrieval, policy, sandbox actions, drafts, audit log, Claude arm |
| Evaluate | `scripts/run_eval.py`, `outputs/pilot{1,2}/results.json`, `docs/figures/` |
| Decide | [`docs/04_pilot_readout.md`](docs/04_pilot_readout.md) |
| Hand off | [`docs/05_handoff_runbook.md`](docs/05_handoff_runbook.md), [`docs/model_card.md`](docs/model_card.md) |
| Use | `api/` (Flask) + `web/` (React 18 + TypeScript): triage console, review queue, evaluation dashboard, audit log |

## How a ticket is handled

```
ticket ─► redact PII ─► detect language, extract service tag / order / case number
       ─► hard safety rules ───────────────────────────────► ESCALATE
       ─► intent model (TF-IDF + embeddings, calibrated)
            critical score ≥ τ ───────────────────────────► ESCALATE
            instruction aimed at the system ──────────────► person reviews
            two requests ─────────────────────────────────► person reviews
            close look-alike of a never-automate intent ──► person reviews
            never-automated intent, or confidence < λ ────► person reviews, with draft + evidence
            non-English (if the policy says so) ──────────► person reviews
            missing identifier ───────────────────────────► ask for it (automated)
            KB answer not in retrieval top 2 ─────────────► person reviews
            otherwise ─► KB reply / read-only lookup / scheduling link (sandbox)
every decision ─► append-only audit log ─► reviewer approve / edit / reject
```

λ (automation) and τ (critical) are chosen on a calibration set with Learn-then-Test and exact binomial bounds, then frozen and committed before the held-out set is scored.

## Key numbers (held-out, scored once)

| | Pilot 1 | Pilot 2 |
|---|---|---|
| Intent accuracy | 68.4% | 86.2% |
| Routing accuracy | 77.6% | 88.9% |
| Critical recall (95% lower bound) | 99.0% (96.8%) | 97.5% (94.3%) |
| Automated | 10.3% at 94.2% accuracy | 0% (no threshold certifiable) |
| Net per 1,000 tickets (illustrative) | −$1,046 | −$1,269 |
| Decision | NO-GO | NO-GO |

## Quick start

```bash
pip install -r requirements-dev.txt
cd web && npm ci && npm run build && cd ..
python api/app.py          # http://localhost:5000
pytest -q                  # 21 tests
```

Run the Claude arm under the same protocol (needs an API key; pass current model id and prices):

```bash
python scripts/run_llm_eval.py --model <model-id> --price-in <usd/Mtok> --price-out <usd/Mtok> --limit 100
```

## Stack

Python 3.13, scikit-learn (training only), numpy-only inference (TF-IDF reimplemented and tested against scikit-learn), WordLlama static embeddings, BM25 + embedding hybrid retrieval, SciPy exact intervals, Flask 3, SQLite, React 18 + TypeScript + Vite, hand-written SVG charts, Anthropic SDK for the LLM arm.
