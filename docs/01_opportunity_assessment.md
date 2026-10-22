# 1. Opportunity assessment

**Setting.** A service-operations team at a fictional PC, monitor and server vendor, *Halden Devices*, receives customer service requests by email and web form: troubleshooting questions, warranty questions, parts and dispatch follow-ups, scheduling, billing, and occasional enterprise outages. Halden Devices, its products, its tickets and its knowledge base are invented for this pilot. Nothing here describes any real company's tickets, systems or volumes.

**Question.** Which of the team's repetitive tasks should get an AI or automation pilot first?

## Candidates

| # | Candidate | What it would do |
|---|---|---|
| A | Service-request triage, routing and selective auto-resolution | Classify each incoming request, route it to the right queue, auto-handle only the low-risk routine cases, and send everything risky or uncertain to a person with evidence attached |
| B | Warranty-claim document checks | Extract fields from claim forms and proof-of-purchase documents, validate them, and route exceptions |
| C | SLA-breach risk prediction | Predict which open cases will miss their resolution target and re-prioritize the queue |
| D | Agent knowledge assistant | Retrieval-backed answers to agents' procedure questions |
| E | Autonomous dispatch and parts ordering | Let the system decide on onsite visits and part shipments directly |
| F | Automated weekly operations report | Scheduled script that builds the volume, backlog and SLA report |

## Scoring rubric

Each criterion is scored 1 (poor) to 5 (strong). Risk is scored so that 5 means *low* risk. Weights were set before scoring.

| Criterion | Weight | What a 5 means |
|---|---|---|
| Value | 0.30 | High volume × handling time touched; frees meaningful analyst hours |
| Feasibility | 0.20 | Data and tools available now; can be prototyped without system integration |
| Risk (inverse) | 0.20 | A wrong output is cheap to catch and reverse; no uncontrolled changes to customer records or money |
| Measurability | 0.15 | Success can be measured against a baseline on held-out data |
| Reusability | 0.15 | Components (classification, retrieval, review queue, audit log) carry over to other workflows |

## Scores

| # | Value | Feasibility | Risk (inv.) | Measurability | Reusability | **Weighted** | Decision |
|---|---|---|---|---|---|---|---|
| A | 5 | 4 | 4 | 5 | 5 | **4.60** | **Pilot now** |
| B | 4 | 2 | 4 | 4 | 4 | 3.60 | Defer (no claim documents available to prototype on); third in line |
| C | 4 | 2 | 5 | 4 | 3 | 3.65 | Next in line once timestamped resolution history is available; can reuse A's classifier as features |
| D | 3 | 4 | 4 | 3 | 4 | 3.55 | Fold into A as its retrieval layer |
| E | 4 | 2 | 1 | 3 | 2 | 2.55 | **Reject** |
| F | 2 | 5 | 5 | 2 | 2 | 3.20 | Quick win, not an AI pilot; hand to an analyst as a scripting task |

The weighted score is computed in `docs/opportunity_scores.csv` with the weights above.

## Why E is rejected

Autonomous dispatch and parts ordering commits money and changes customer records on the strength of a model output. A wrong onsite dispatch or a wrong part costs real money and time, mistakes are hard to reverse once a technician or a courier is moving, and the prototype would need write access to order and scheduling systems. That fails the pilot's own guardrail: no uncontrolled changes to customer records. The better path is A's design: recommend the dispatch with evidence and let a person approve it.

## Why A goes first

- It touches every incoming request, so even partial automation moves the workload.
- It can be built and tested without integrating with any production system.
- Its risk can be bounded: the design automates only what it can show it handles safely, and the threshold for "safe" is set on data the test set never sees.
- Its parts (classification, extraction, retrieval, review queue, audit log) are the reusable core of B, C and D.

## What A must prove

See `02_pilot_charter.md`: go/no-go criteria were fixed there before any test-set result was computed.
