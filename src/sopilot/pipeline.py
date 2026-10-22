"""End-to-end triage: evidence gathering (threshold-free) + decision policy.

    evidence = pipeline.analyze(texts)          # models, guards, extraction, retrieval
    decision = decide(evidence[i], params)      # cheap; used for threshold sweeps
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import sandbox
from .drafts import draft
from .extract import detect_language, extract_fields, extract_product
from .guards import detect_injection, hard_escalation, redact_pii
from .retrieval import Retriever
from .scorers import (Embedder, EmbedScorer, EnsembleScorer, RulesScorer, TfidfScorer)
from .taxonomy import AUTOMATED_ACTIONS, CRITICAL_INTENTS, INTENT_NAMES, INTENTS

ROOT = Path(__file__).resolve().parents[2]
CRIT_IDX = [INTENT_NAMES.index(c) for c in CRITICAL_INTENTS]
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_SKIP = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon)|thanks|thank you|regards|best|cheers|kind regards|"
                   r"dzień dobry|witam|cześć|guten tag|hallo|hola|buenos días|saludos|gracias|pozdrawiam|viele grüße|danke)\b", re.I)


@dataclass
class Params:
    auto_threshold: float = 0.9      # lambda: min calibrated confidence to automate
    critical_threshold: float = 0.3  # tau_c: min P(critical intent) to escalate
    multi_threshold: float = 0.7     # per-sentence confidence for the multi-request detector (fixed a priori)
    non_english: str = "allow"       # "allow" or "review"
    require_evidence: bool = True    # AUTO_REPLY_KB needs the intent's article in retrieval top-2
    version: str = "policy-v1"


def sentences(text: str):
    out = []
    for s in _SENT.split(text):
        s = s.strip()
        if len(s.split()) >= 4 and not _SKIP.match(s) and "@" not in s and "[EMAIL]" not in s:
            out.append(s)
    return out


class Pipeline:
    def __init__(self, scorer, retriever, model_version: str):
        self.scorer, self.retriever, self.model_version = scorer, retriever, model_version

    @classmethod
    def load(cls, art: Path | None = None, scorer_name: str | None = None, embedder=None):
        art = Path(art or ROOT / "artifacts")
        meta = json.loads((art / "meta.json").read_text())
        name = scorer_name or meta["chosen_scorer"]
        articles = json.loads((ROOT / "data" / "kb" / "articles.json").read_text(encoding="utf-8"))
        if name == "rules":
            return cls(RulesScorer(meta["T_rules"]), Retriever(articles), "rules")
        embedder = embedder or _load_embedder(art)
        tf = TfidfScorer.load(art / "tfidf")
        e = np.load(art / "embed_lr.npz")
        em = EmbedScorer(embedder, e["coef"], e["intercept"], float(e["temperature"]))
        scorer = {"tfidf": tf, "embed": em, "ensemble": EnsembleScorer([tf, em], meta["T_ensemble"])}[name]
        return cls(scorer, Retriever(articles, embedder), f"{name}-dev{meta['n_train']}")

    # ---------------------------------------------------------------- evidence
    def analyze(self, texts):
        t0 = time.perf_counter()
        probs = self.scorer.predict_proba(texts)
        sents = [sentences(redact_pii(t)[0]) for t in texts]
        flat = [s for ss in sents for s in ss]
        sp = self.scorer.predict_proba(flat) if flat else np.zeros((0, len(INTENT_NAMES)))
        per = (time.perf_counter() - t0) * 1000 / max(1, len(texts))
        out, k = [], 0
        for i, t in enumerate(texts):
            t1 = time.perf_counter()
            red, pii = redact_pii(t)
            p = probs[i]
            top = np.argsort(-p)[:3]
            n = len(sents[i])
            sent_preds = [(INTENT_NAMES[int(np.argmax(sp[k + j]))], float(sp[k + j].max())) for j in range(n)]
            k += n
            intent = INTENT_NAMES[int(top[0])]
            ev = {
                "redacted_text": red, "pii_found": pii, "language": detect_language(red),
                "fields": extract_fields(t), "product": extract_product(t),
                "probs": p, "intent": intent, "confidence": float(p[top[0]]),
                "top3": [(INTENT_NAMES[int(j)], round(float(p[j]), 4)) for j in top],
                "p_critical": float(p[CRIT_IDX].sum()),
                "critical_intent": CRITICAL_INTENTS[int(np.argmax(p[CRIT_IDX]))],
                "guard_hits": hard_escalation(red), "injection": detect_injection(red),
                "sentence_preds": sent_preds,
                "retrieval": self.retriever.search(red, k=3),
            }
            ev["latency_ms"] = per + (time.perf_counter() - t1) * 1000
            out.append(ev)
        return out

    def triage(self, text: str, params: Params, audit=None, ticket_ref=None):
        t0 = time.perf_counter()
        ev = self.analyze([text])[0]
        d = decide(ev, params, self.retriever, model_version=self.model_version)
        d["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if audit is not None:
            d["audit_id"] = audit.record(d, ticket_ref)
        return d


def _load_embedder(art: Path):
    f = art / "embedder.npz"
    if f.exists():  # deploy bundle: truncated matrix + tokenizer json
        z = np.load(f)
        return Embedder(str(z["tokenizer"]), z["matrix"].astype(np.float32))
    return Embedder.from_wordllama()


def multi_request(ev, thr):
    confident = {intent for intent, c in ev["sentence_preds"] if c >= thr}
    return sorted(confident) if len(confident) >= 2 else []


def decide(ev, params: Params, retriever=None, model_version: str = ""):
    """Apply the policy. Returns a decision dict; `reasons` explains every step taken."""
    reasons = []
    intent, conf = ev["intent"], ev["confidence"]
    action = None

    if ev["guard_hits"]:
        gi, phrase = ev["guard_hits"][0]
        intent, action = gi, "ESCALATE"
        reasons.append(f"Hard rule: '{phrase}' matches the {gi.replace('_', ' ')} escalation list")
    elif ev["p_critical"] >= params.critical_threshold:
        intent, action = ev["critical_intent"], "ESCALATE"
        reasons.append(f"Model puts {ev['p_critical']:.0%} on critical intents (threshold {params.critical_threshold:.0%})")
    elif ev["injection"]:
        action = "HUMAN_REVIEW"
        reasons.append(f"Text addressed to the system detected ('{ev['injection'][0]}'); a person must handle it")
    else:
        multi = multi_request(ev, params.multi_threshold)
        it = INTENTS[intent]
        if multi:
            action = "HUMAN_REVIEW"
            reasons.append(f"Two separate requests detected ({', '.join(m.replace('_', ' ') for m in multi)})")
        elif it.action not in AUTOMATED_ACTIONS:
            action = "HUMAN_REVIEW"
            reasons.append(f"{intent.replace('_', ' ')} is never automated; routed to {it.queue.replace('_', ' ')} with a draft")
        elif conf < params.auto_threshold:
            action = "HUMAN_REVIEW"
            reasons.append(f"Confidence {conf:.0%} is below the automation threshold {params.auto_threshold:.0%}")
        elif params.non_english == "review" and ev["language"] != "en":
            action = "HUMAN_REVIEW"
            reasons.append(f"Non-English ticket ({ev['language']}); policy sends these to a person")
        else:
            missing = [f for f in it.required if f not in ev["fields"]]
            if missing:
                action = "REQUEST_INFO"
                reasons.append(f"Automatable, but missing {', '.join(missing)}")
            elif it.action == "AUTO_REPLY_KB" and params.require_evidence and \
                    not any(r["id"] in it.kb for r in ev["retrieval"][:2]):
                action = "HUMAN_REVIEW"
                reasons.append("Retrieval did not return the matching procedure in the top 2; no grounded answer")
            else:
                action = it.action
                reasons.append(f"Confidence {conf:.0%} ≥ {params.auto_threshold:.0%}; {intent.replace('_', ' ')} is on the automation list")

    it = INTENTS[intent]
    missing = [f for f in it.required if f not in ev["fields"]]
    article = retriever.get(it.kb[0]) if (retriever is not None and it.kb) else None
    lookup = None
    if action == "AUTO_LOOKUP":
        field, fn = sandbox.LOOKUPS[intent]
        lookup = fn(ev["fields"][field])
    elif action == "AUTO_SCHEDULE_LINK":
        lookup = sandbox.scheduling_link(ev["fields"]["case_number"])
    dr = draft(action, intent, article, lookup, missing) if retriever is not None else None
    return {
        "action": action, "automated": action in AUTOMATED_ACTIONS, "intent": intent, "queue": it.queue,
        "priority": it.priority, "confidence": round(conf, 4), "p_critical": round(ev["p_critical"], 4),
        "top3": ev["top3"], "reasons": reasons, "fields": ev["fields"], "missing_fields": missing,
        "language": ev["language"], "pii_redacted": ev["pii_found"], "injection": ev["injection"],
        "guard_hits": ev["guard_hits"], "retrieval": ev["retrieval"], "lookup": lookup, "draft": dr,
        "redacted_text": ev["redacted_text"], "model_version": model_version, "policy_version": params.version,
        "params": asdict(params),
    }
