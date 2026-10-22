# 2. Pilot charter (pre-registered)

Written and committed **before** any model was trained or any test-set result was computed. The git history shows this file's commit preceding the first results commit. Changes after that point are listed at the bottom with a reason, and do not move the go/no-go thresholds.

## Objective

Show whether service-request triage at Halden Devices (fictional) can be partly automated **without** automating cases a person should handle, and quantify how much work that removes.

## Scope

In scope: classifying each request into an intent and a queue, extracting identifiers, retrieving procedures, choosing an action, drafting replies, a reviewer approval step, and an audit log.

Out of scope: any write to customer records, orders, refunds or dispatch systems. The prototype's "automations" are read-only lookups, knowledge-base replies, requests for missing information, and self-scheduling links, all executed in a sandbox.

## Actions the system may take

| Action | Automated? | Examples |
|---|---|---|
| `AUTO_REPLY_KB` | yes | Send the matching knowledge-base procedure |
| `AUTO_LOOKUP` | yes | Read-only status lookups (warranty status, part order status, refund status, invoice copy) |
| `AUTO_SCHEDULE_LINK` | yes | Send a self-scheduling or rescheduling link |
| `REQUEST_INFO` | yes | Ask for a missing service tag, order number or case number |
| `HUMAN_REVIEW` | no | Route to the right queue with a draft and evidence for a person to approve |
| `ESCALATE` | no | Priority route to a specialist (safety, security, legal, privacy, data loss, enterprise outage) |

The correct action for every ticket is defined by the labeling guide (`03_labeling_guide.md`), not by the model.

## Data and splits

All tickets are synthetic and labeled by construction under the labeling guide. Phrasings are split by template family, so test tickets use problem descriptions the models never saw.

| Split | Use |
|---|---|
| `dev` | Training and development only |
| `val` | Calibration, choosing the scorer, choosing thresholds |
| `test` | Scored **once**, after all choices are frozen |
| `shift` | New product family, chat-style phrasing, more non-English tickets: a stress test of deployment drift |
| `handwritten` | Free-written, longer, messier tickets not produced by the template generator |

## Metrics (definitions fixed here)

- **Automated coverage**: share of tickets the system handles with an automated action.
- **Automated accuracy**: among automated tickets, share where the action and intent both match the gold label.
- **Inappropriate automation**: among automated tickets, share whose gold action is `HUMAN_REVIEW` or `ESCALATE`.
- **Critical recall**: among gold-critical tickets, share the system escalates. **Critical misrouting** = 1 − critical recall.
- **Escalation precision**: among escalated tickets, share that are gold-critical.
- **Routing accuracy**: share of all tickets whose predicted queue matches the gold queue.
- **Human workload**: share of tickets sent to people (`HUMAN_REVIEW` + `ESCALATE`).
- **Latency** (p50, p95 per ticket) and **cost per ticket**.
- **Net value per 1,000 tickets**: analyst minutes saved, minus review time, error costs and maintenance, converted at a stated hourly cost (see `economics` in the code; all inputs are illustrative assumptions).

Intervals: Clopper-Pearson (exact binomial) for single rates; for differences between systems, a cluster bootstrap that resamples template families, because tickets built from the same phrasing are not independent.

## Threshold-setting protocol (validation set only)

1. **Scorer choice.** Pick the scorer with the lowest area under the risk-coverage curve on `val`.
2. **Automation threshold.** Choose the confidence threshold with Learn-then-Test fixed-sequence testing: go from strict to permissive thresholds and stop at the last one where an exact binomial test rejects "error rate among automated tickets > 4%" at δ = 0.05. This gives a finite-sample guarantee, under exchangeability, that automated error stays at or below 4% with 95% confidence.
3. **Critical threshold.** Choose the critical-probability threshold so that, combined with the hard guard rules, the one-sided 95% Clopper-Pearson lower bound on critical recall on `val` is at least 0.95.
4. Freeze everything, then score `test`, `shift` and `handwritten` once.

## Go / no-go criteria (on `test` unless noted)

| ID | Criterion | Threshold |
|---|---|---|
| G1 | Critical recall | ≥ 0.98, with 95% lower bound ≥ 0.95 |
| G2 | Inappropriate automation | ≤ 2% of automated tickets, with 95% upper bound ≤ 3% |
| G3 | Automated accuracy | ≥ 95% |
| G4 | Automated coverage | ≥ 30% |
| G5 | Routing accuracy | ≥ 85% |
| G6 | Shift set | Critical recall ≥ 0.95 and inappropriate automation ≤ 5% |
| G7 | Economics | Net value per 1,000 tickets > 0 under base **and** pessimistic assumptions |

## Decision rule

- **GO** (move to a supervised production pilot): G1 through G7 all pass.
- **NARROW GO**: G1 and G2 pass, but G3, G4, G6 or G7 passes only when automation is limited to named intents. Automate only those intents and send the rest to people.
- **NO-GO**: G1 or G2 fails. No automation; the classifier can still be used for routing suggestions to people.

## Comparison arms

1. **All-human baseline**: every ticket goes to a person (coverage 0, the cost reference).
2. **Keyword rules** written from the labeling guide.
3. **TF-IDF + logistic regression.**
4. **Pretrained static embeddings (WordLlama) + logistic regression.**
5. **Ensemble of 3 and 4.**
6. **LLM arms** (Claude, zero-shot and with retrieval): fully wired, run when an API key is available, evaluated under this same protocol.

Each arm is wrapped in the same guards, policy and threshold protocol, so differences come from the scorer.

## Change log

None of these changes moves a go/no-go threshold. The test split was not scored or read before any of them.

1. **Phrasing bank doubled (dev only informed it).** The first data version had 12 phrasings per intent (6 for training). A first training run, and one exploratory look at validation intent accuracy (about 63%), showed the learned models were in a cold-start regime: six example sentences per intent. The bank was expanded to 24 phrasings per intent (14 dev / 4 val / 6 test) and every split was regenerated. The 6-phrasing condition is kept as a learning-curve analysis.
2. **Scorer choice and calibration moved off val.** Both now use template-grouped out-of-fold predictions on dev, so val is used only for thresholds and its guarantee is not spent on model selection. This tightens the protocol.
3. **First threshold run on val (v1) exposed two problems, and val was re-sampled.**
   - *Start rule bug.* The Learn-then-Test search skipped thresholds with fewer than 50 automated tickets, but with α = 4% and δ = 5% even zero errors cannot reject below 74 tickets, so the fixed sequence stopped at once. The start rule is now the label-free minimum n = ⌈log δ / log(1 − α)⌉ = 74.
   - *Weak hard rules.* The guard rules caught 64% of critical val tickets because they were written against the first phrasing batch. Rules were extended using **dev** tickets they missed (dev recall 265/270, zero false positives on dev). Because the rules are now fitted to dev phrasings, their recall on dev is optimistic by construction.
   - Because val v1 had been seen in aggregate, the thresholds were re-chosen on a **freshly sampled val (v2)** from the same validation phrasing families with a new seed. Test was never touched.
4. **Pre-set non-English rule.** After λ is chosen, if automated non-English tickets on val have an error rate above α, the policy sends all non-English tickets to people. Decided before scoring test.
