# 2b. Pilot 2 charter (pre-registered)

Written after Pilot 1 was scored (NO-GO) and **before** the Pilot 2 holdout data existed. The go/no-go criteria G1 through G7 and the decision rule are unchanged from `02_pilot_charter.md`.

## What Pilot 1 showed

| Finding | Evidence (Pilot 1 test) |
|---|---|
| Escalation, not automation, decides the economics | Reaching 99% critical recall needed a critical threshold of 0.04: 29% of tickets escalated, 57% of them unnecessarily (−$972 per 1,000 tickets) |
| Hand-written safety rules overfit the phrasings they were written from | 98% recall on dev (in-sample), 78% on test |
| Multi-request detection is the largest source of inappropriate automation | 5 of 9 automated errors; detector recall 57% |
| The automation guarantee did not transfer across phrasings | Automated error 1.1% on val, 5.8% on test; tickets sharing a phrasing are correlated, so 4 phrasings per intent was a thin calibration set |
| Lookups fire on look-alike requests that need a person | warranty_status lookups on ownership-transfer and extension requests |

## Changes for Pilot 2

1. **More training phrasings.** Train on dev + val (18 phrasings per intent).
2. **Larger, independent calibration set.** Pilot 1's test split (6 phrasings per intent, 1,500 tickets) becomes the calibration set. It is not used for training.
3. **Dedicated critical classifier.** A binary critical vs. non-critical model (TF-IDF and embedding logistic regressions, averaged, Platt-calibrated on grouped out-of-fold predictions). The critical signal used by the policy (intent-sum, binary, or their average) is chosen by out-of-fold average precision on the training data.
4. **Cue-aware multi-request detector.** A sentence containing a cue such as "also", "separately", "unrelated", "another thing" or "as well", whose own predicted intent differs from the ticket's intent with probability ≥ 0.5, marks the ticket as multi-request. The Pilot 1 detector is kept, with its sentence threshold raised from 0.7 to 0.85 to cut false positives.
5. **Sibling guard.** If the top intent is automatable but a never-automate intent in the same queue has probability ≥ 0.10, the ticket goes to a person.
6. **Tighter automation target.** Learn-then-Test at α = 3% (was 4%), δ = 5%, to leave margin for phrasing shift. Go/no-go thresholds are unchanged.
7. **Data fix.** Typo noise no longer corrupts identifiers (Pilot 1 had one test ticket where a typo turned a valid service tag invalid, so its gold label was wrong).

## Pilot 2 holdout

- A new batch of 6 English phrasings per intent, written after this charter and never used in training or calibration, plus 1 new phrasing per language for the 12 multilingual intents, new critical-override sentences, new prompt-injection strings and new secondary-request sentences.
- `holdout_v2` (1,500 tickets), `shift_v2` (800, new products, chat style, typos, more non-English), `paraphrase_v2` (150 cases × 6 phrasings), and the unchanged 60 hand-written tickets.
- Scored **once**, after thresholds are frozen and committed.

## Change log

1. **Reporting rule added after the holdout was scored.** When nothing is automated, G2 (inappropriate automation) and G3 (automated accuracy) are reported as "not applicable" and do not count as failures. The first scoring script had marked G2 as failed because its upper bound was undefined. The decision is unchanged either way, because G1 failed.

## Decision rule

Same as Pilot 1. If Pilot 2 is GO or NARROW GO, the recommendation is a supervised production pilot with the monitoring plan in the runbook. If it is NO-GO, automation stays off and the system is assessed as a routing and flagging assistant only.
