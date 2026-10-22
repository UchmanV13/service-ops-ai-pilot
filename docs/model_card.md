# Model card: Halden triage intent model (Pilot 2)

**Intended use.** Suggest an intent and queue for incoming service requests at a fictional hardware vendor, flag possibly critical tickets for a specialist, and, only under a certified threshold, automate read-only replies. Not for decisions about refunds, replacements, dispatch, or any change to customer records.

**Model.** Average of two multinomial logistic regressions over 33 intents: (1) word 1–2-gram and character 2–5-gram TF-IDF; (2) mean-pooled WordLlama static token embeddings (256 dimensions, pretrained, distributed in the `wordllama` wheel). Temperature-scaled on template-grouped out-of-fold predictions. Critical score = summed probability of the 7 critical intents. Runs on CPU in a few milliseconds per ticket.

**Training data.** 3,600 synthetic tickets (dev + val), 18 English phrasings per intent plus Polish, German and Spanish phrasings for 12 intents, generated from templates under the labeling guide. No real customer data.

**Evaluation.** One scoring of 1,500 held-out tickets whose phrasings were written after the model was designed: intent accuracy 86.2%, routing 88.9%, critical recall 97.5% (95% lower bound 94.3%), calibration error 2.9 points (15.8 before temperature scaling). Shifted set (new products, chat style, typos, more non-English): routing 77.5%, critical recall 96.3%. Hand-written set (60): routing 85.0%, critical recall 100%.

**Known limitations.**
- Learned from 18 phrasings per intent; accuracy is still rising with more variety (learning curve: 68% at 3, 87% at 18).
- Non-English intents are thinly covered (German intent accuracy 77.5% on the holdout).
- Confuses near-neighbors: schedule vs. reschedule, warranty status vs. extension or transfer, return label vs. return request.
- The labels encode one author's guide; there is no human agreement measurement yet.
- Confidence is calibrated on synthetic phrasing families; it is not evidence of calibration on real traffic.

**Ethical and safety considerations.** PII is redacted before any model or log sees the text. Critical topics (safety, security, legal, privacy, data loss, outages) always go to people. The model never authorizes an action by itself: actions come from an allow-list, and anything outside it needs human approval.
