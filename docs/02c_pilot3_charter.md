# 2c. Pilot 3 charter (pre-registered): Claude arm on a fresh holdout

Written after Pilot 2 was scored (NO-GO) and **before** any Claude-arm output on the Pilot 3 holdout exists. The go/no-go criteria G1 through G7 and the decision rule are unchanged from `02_pilot_charter.md`.

## Question

Pilot 2 certified no automation threshold: the local models' confidence could not meet the 3% error bound at useful coverage. Does a large language model, with confidence taken from agreement across repeated answers, certify automation where the local models did not, without losing critical-ticket recall?

## What Pilot 2 showed (inputs to this design)

| Finding | Evidence (Pilot 2 holdout_v2) |
|---|---|
| No automation threshold certifiable | Learn-then-Test found none at alpha = 3%, delta = 5% |
| Escalation carries the economics | Critical recall 97.5% (95% lower bound 94.3%); net -$1,269 per 1,000 tickets (illustrative inputs) |
| Intent accuracy limits routing | Intent 86.2%, routing 88.9% |

## Arm definition (frozen at the commit of this charter)

- **Model:** `claude-sonnet-5-5`. **Confidence mode:** `vote` (primary), 5 answers per ticket, confidence = share of agreeing answers. The `verbalized` mode may be run afterward and reported as exploratory only; it does not enter the decision.
- **Everything else is the Pilot 2 pipeline:** PII redaction, hard safety rules, cue-aware multi-request detector (0.85), sibling guard (0.10), retrieval evidence check, sandbox actions, audit log. Only the intent scorer changes.
- **Prompt and code:** `src/sopilot/llm.py` and `scripts/run_llm_eval.py` as of this commit. No prompt or policy edits after this commit without a change-log entry.
- **Threshold protocol:** critical threshold and automation threshold are chosen on the calibration set only (Learn-then-Test, alpha = 3%, delta = 5%), written to `outputs/pilot3_llm/thresholds.json`, and committed before the holdout is scored.

## Data

- **Calibration:** `holdout_v2` (1,500 tickets). The local arms were scored on it in Pilot 2, so it is not fresh for them; it is disclosed here as calibration data for an arm that has never been fitted to it. Any dry runs (`--limit`) use calibration data only.
- **Holdout:** `holdout_v3`, **to be generated after this charter is committed**: 6 new English phrasings per intent, 1 new phrasing per language for the multilingual intents, new critical-override, injection and secondary-request sentences, none seen in dev, val, test or holdout_v2. It must exist and be committed before any Claude call touches it.
- **Baseline:** the Pilot 2 frozen local policy is scored once on `holdout_v3` with no retuning, so the comparison is on the same tickets.

## Criteria and decision rule

Unchanged: G1 critical recall, G2 inappropriate automation, G3 automated accuracy, G4 coverage, G5 routing accuracy, G6 shift set, G7 economics (see `02_pilot_charter.md`). Where nothing is automated, G2 and G3 are reported as not applicable, as in Pilot 2. GO or NARROW GO means a supervised pilot on real tickets; NO-GO means automation stays off.

## Rules of the run

1. One scoring run on `holdout_v3`. Results are reported whatever they are.
2. Budget cap of USD 40 total API spend; if the cap would be exceeded the run stops and is reported as incomplete.
3. Calibration and cost are recorded in `outputs/pilot3_llm/results.json`.
4. Anything found wrong after scoring is added to the change log below and does not change the decision.

## Threats to validity (stated in advance)

- Synthetic tickets from one author's templates share style; real traffic will differ, so a GO is a case for a real-data pilot, not for deployment.
- The model may have seen similar public support text; this cannot be checked.
- Labels follow one author's guide; human agreement is still unmeasured.
- Vote-share confidence is only as good as its calibration on the calibration set.

## Change log

(none yet)
