# 4. Pilot readout: service-request triage at Halden Devices

*Halden Devices is fictional. All tickets are synthetic or hand-written for this pilot, and every cost input is an illustrative assumption. The numbers show how the system behaves under its own labeling rules, not how it would perform on any real company's traffic.*

## Recommendation

**Do not automate customer-facing actions yet. Run one more pilot, on real labeled tickets and with the Claude arm, under the same protocol.**

Two pre-registered pilots both came back **NO-GO**:

| | Pilot 1 | Pilot 2 |
|---|---|---|
| Held-out set (scored once) | `test`, 1,500 tickets | `holdout_v2`, 1,500 tickets, phrasings written after the Pilot 2 charter |
| Automation threshold | 0.945, certified on val | none certifiable on the calibration set |
| Automated | 10.3% | 0% |
| Automated accuracy | 94.2% | n/a |
| Inappropriate automation | 4.5% (95% upper bound 8.4%) | n/a |
| Critical recall | 99.0% (lower bound 96.8%) | 97.5% (lower bound 94.3%) |
| Escalation precision | 43.2% | 54.8% |
| Routing accuracy | 77.6% | 88.9% |
| Intent accuracy | 68.4% | 86.2% |
| Net value per 1,000 tickets (base / pessimistic) | −$1,046 / −$4,862 | −$1,269 / −$6,207 |
| Decision | NO-GO (G2, G3, G4, G5, G7 failed) | NO-GO (G1, G4, G7 failed) |

## What the pilots proved

1. **Iteration worked where it was aimed.** On wording it never saw, the intent model went from 68.4% to 86.2% accuracy, routing from 77.6% to 88.9% (passing G5), multi-request detection from 57% to 96% recall, and paraphrase stability (the same case written six ways gets the same action) from 55% to 89%.
2. **Escalation, not automation, decides the economics.** To hold critical recall near 98%, the critical threshold falls to 0.03–0.04, and about half of all escalations are not critical. In Pilot 1, false escalations cost $972 per 1,000 tickets and two missed critical cases another $667, against $490 of automation savings. Pilot 2 breaks even only if a missed critical ticket costs less than about $24.
3. **Hand-written rules overfit the data they were written from.** The safety rules caught 98% of critical tickets on dev and 78% (Pilot 1) and 66% (Pilot 2) on new phrasings. The injection patterns caught 33/33 Pilot 1 injections and 15/32 new ones. The learned critical score, not the rules, carries recall (removing it drops recall to 66–78%).
4. **A finite-sample guarantee is only as good as its calibration set.** Pilot 1's threshold kept automated error at 1.1% on validation and 5.8% on test. Tickets that share a phrasing are correlated, so 4 phrasings per intent behaved like a much smaller sample than 1,200 tickets suggests. Pilot 2 tightened the target (3%) and used a larger calibration set, and no threshold passed.
5. **A dedicated critical classifier did not help.** By the pre-registered choice rule (out-of-fold average precision), the binary model (0.950) lost to summing the intent model's critical probabilities (0.974).
6. **The scorer chosen on training data was not the best on the holdout.** The ensemble won on out-of-fold AURC; on Pilot 2's holdout, TF-IDF alone routed better (93.5% vs 88.9%) with fewer false escalations (76% precision) but lower critical recall (95.6%). Choosing on the holdout would have been cheating, so the ensemble stands.
7. **Safety held where it was designed in.** No PII leaked after redaction (0 of 820 tickets with contact details). Injections appended to every automated Pilot 1 ticket stopped automation in 154 of 154. Ticket text cannot trigger an action, because actions are an allow-list of read-only lookups, KB replies and scheduling links.

## Why the decision is not "this cannot work"

On Pilot 2's holdout, a 0.95 threshold would have automated 32.5% of tickets at 0.8% error, and a 0.80 threshold would have turned net value positive (+$137 per 1,000). Neither was certified in advance, so neither is claimed. They are the reason one more pilot is worth running.

## Conditions for Pilot 3

1. **Real data.** Label a sample of real tickets with the labeling guide. Two people label the 150-ticket blind sheet first (`scripts/agreement.py` reports Cohen's kappa) so label noise is measured, not assumed.
2. **Claude arm.** Run `scripts/run_llm_eval.py` (already wired: same guards, policy, protocol, cost per ticket from real token usage). A zero-shot model removes the cold-start limit the learning curve shows: 68% accuracy at 3 phrasings per intent, 87% at 18.
3. **Cluster-aware calibration.** Calibrate on data from the same period and channels the policy will govern, and bound error per phrasing cluster, not per ticket.
4. **Fix the two gaps the calibration set exposed.** A multi-request cue sentence can carry the ticket's dominant intent, and warranty look-alikes (ownership transfer, extension) can pass the sibling guard.
5. **Price escalation realistically.** A senior-analyst "possible critical" queue at analyst rates changes the economics more than any model change. It is the largest swing in Pilot 1's sensitivity analysis.

## Known issues

- **Label artifact in Pilot 1 data.** Typo noise corrupted identifiers in 7 test tickets and 32 shift tickets, so their gold label says the identifier is present when the text no longer contains a valid one. One of Pilot 1's 9 automated errors is this artifact; correcting it moves automated accuracy from 94.2% to 94.8% and does not change the decision. Pilot 2 data protects identifiers.
- **Author overlap.** One author wrote the templates, the labeling rules and the safety rules. The hand-written tickets and the batch-3 holdout reduce, but do not remove, this optimism.
- **Synthetic economics.** All cost inputs are placeholders. The model charges the system for every missed critical ticket and assumes the all-human desk misses none.

## Figures

`docs/figures/`: threshold sweep (fig1), critical trade-off (fig2), learning curve (fig3), economics (fig4), calibration (fig5), pilot comparison (fig6).
