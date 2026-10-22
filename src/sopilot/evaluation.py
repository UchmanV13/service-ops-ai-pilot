"""Scoring decisions against gold labels, and the threshold-setting protocol."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

from .metrics import binom_pvalue_risk_above, clopper_pearson, cluster_bootstrap, cp_lower, cp_upper
from .pipeline import Params, decide
from .taxonomy import AUTOMATED_ACTIONS, HUMAN_ACTIONS

ROOT = Path(__file__).resolve().parents[2]


def load(split):
    return [json.loads(line) for line in open(ROOT / "data" / "tickets" / f"{split}.jsonl", encoding="utf-8")]


def outcome(row, d):
    g = row["gold"]
    auto = d["action"] in AUTOMATED_ACTIONS
    correct_auto = auto and d["action"] == g["action"] and d["intent"] == g["intent"]
    inappropriate = auto and g["action"] in HUMAN_ACTIONS
    return {
        "auto": auto, "correct_auto": correct_auto, "inappropriate": inappropriate,
        "wrong_auto": auto and not correct_auto and not inappropriate,
        "auto_error": auto and not correct_auto,
        "critical": g["critical"], "escalated": d["action"] == "ESCALATE",
        "queue_ok": d["queue"] == g["queue"], "intent_ok": d["intent"] == g["intent"],
        "action_ok": d["action"] == g["action"], "family": row["template_family"], "language": row["language"],
        "gold_intent": g["intent"], "pred_intent": d["intent"], "gold_action": g["action"], "pred_action": d["action"],
    }


def _rate(k, n):
    return {"k": int(k), "n": int(n), "rate": (k / n) if n else None, "ci95": clopper_pearson(int(k), int(n)) if n else None}


def summarize(outs, latencies=None, bootstrap=True):
    n = len(outs)
    auto = [o for o in outs if o["auto"]]
    crit = [o for o in outs if o["critical"]]
    esc = [o for o in outs if o["escalated"]]
    na, nc = len(auto), len(crit)
    k_inapp = sum(o["inappropriate"] for o in auto)
    k_correct = sum(o["correct_auto"] for o in auto)
    k_crit = sum(o["escalated"] for o in crit)
    s = {
        "n": n,
        "automated_coverage": _rate(na, n),
        "automated_accuracy": _rate(k_correct, na),
        "inappropriate_automation": _rate(k_inapp, na) | {"upper95_one_sided": cp_upper(k_inapp, na) if na else None},
        "wrong_intent_automation": _rate(sum(o["wrong_auto"] for o in auto), na),
        "critical_recall": _rate(k_crit, nc) | {"lower95_one_sided": cp_lower(k_crit, nc) if nc else None},
        "escalation_precision": _rate(sum(o["critical"] for o in esc), len(esc)),
        "routing_accuracy": _rate(sum(o["queue_ok"] for o in outs), n),
        "intent_accuracy": _rate(sum(o["intent_ok"] for o in outs), n),
        "action_accuracy": _rate(sum(o["action_ok"] for o in outs), n),
        "human_workload": _rate(n - na, n),
        "action_counts": dict(sorted(_count(o["pred_action"] for o in outs).items())),
    }
    if latencies is not None and len(latencies):
        s["latency_ms"] = {"p50": round(float(np.percentile(latencies, 50)), 2), "p95": round(float(np.percentile(latencies, 95)), 2)}
    if bootstrap and n:
        fam = defaultdict(list)
        for o in outs:
            fam[o["family"]].append(o)
        s["cluster_bootstrap"] = {
            "clusters": len(fam),
            "automated_coverage_ci95": cluster_bootstrap(fam, lambda rows: np.mean([r["auto"] for r in rows])),
            "automated_accuracy_ci95": cluster_bootstrap(
                fam, lambda rows: (np.mean([r["correct_auto"] for r in rows if r["auto"]]) if any(r["auto"] for r in rows) else float("nan"))),
        }
    return s


def _count(it):
    c = defaultdict(int)
    for x in it:
        c[x] += 1
    return dict(c)


def run_policy(rows, evs, params, retriever=None):
    decs = [decide(e, params, retriever) for e in evs]
    return decs, [outcome(r, d) for r, d in zip(rows, decs)]


# --------------------------------------------------------------------------- protocol
def choose_critical_threshold(rows, evs, target_lower=0.95, grid=None):
    """Largest tau_c whose one-sided 95% CP lower bound on critical recall is >= target."""
    grid = grid if grid is not None else np.round(np.arange(0.95, 0.0, -0.01), 2)
    crit = [(r, e) for r, e in zip(rows, evs) if r["gold"]["critical"]]
    trace = []
    best = None
    for tau in grid:
        k = sum(1 for _, e in crit if e["guard_hits"] or e["p_critical"] >= tau)
        lb = cp_lower(k, len(crit))
        trace.append({"tau": float(tau), "recall": k / len(crit), "lower95": lb})
        if lb >= target_lower:
            best = float(tau)
            break  # grid is descending: first passing tau is the largest
    return best, trace


def choose_auto_threshold_ltt(rows, evs, base: Params, alpha=0.04, delta=0.05, n_min=None, grid=None):
    """Learn-then-Test, fixed-sequence: strict -> permissive, stop at the first failure.

    H0(lambda): error rate among automated tickets > alpha. Reject when the exact
    binomial p-value <= delta. Thresholds with fewer than n_min automated
    tickets are skipped (a label-free rule): by default n_min is the smallest n
    at which zero errors could reject, ceil(log(delta) / log(1 - alpha)).
    Returns the most permissive threshold rejected before the first failure.
    """
    import math
    if n_min is None:
        n_min = math.ceil(math.log(delta) / math.log(1 - alpha))
    grid = grid if grid is not None else np.round(np.arange(0.995, 0.299, -0.005), 3)
    chosen, trace = None, []
    for lam in grid:
        p = replace(base, auto_threshold=float(lam))
        _, outs = run_policy(rows, evs, p)
        auto = [o for o in outs if o["auto"]]
        n, k = len(auto), sum(o["auto_error"] for o in auto)
        if n < n_min:
            trace.append({"lambda": float(lam), "n_auto": n, "errors": k, "skipped": True})
            continue
        pv = binom_pvalue_risk_above(k, n, alpha)
        trace.append({"lambda": float(lam), "n_auto": n, "errors": k, "err_rate": k / n, "p_value": pv,
                      "coverage": n / len(rows)})
        if pv <= delta:
            chosen = float(lam)
        else:
            break
    return chosen, trace


def per_intent(outs):
    by = defaultdict(list)
    for o in outs:
        by[o["pred_intent"]].append(o)
    res = {}
    for k, v in sorted(by.items()):
        auto = [o for o in v if o["auto"]]
        res[k] = {"n_pred": len(v), "n_auto": len(auto), "auto_errors": sum(o["auto_error"] for o in auto),
                  "inappropriate": sum(o["inappropriate"] for o in auto)}
    return res


def by_language(outs):
    by = defaultdict(list)
    for o in outs:
        by[o["language"]].append(o)
    return {k: {"n": len(v), "coverage": np.mean([o["auto"] for o in v]),
                "n_auto": sum(o["auto"] for o in v), "auto_errors": sum(o["auto_error"] for o in v),
                "intent_accuracy": np.mean([o["intent_ok"] for o in v]),
                "critical_n": sum(o["critical"] for o in v), "critical_escalated": sum(o["critical"] and o["escalated"] for o in v)}
            for k, v in sorted(by.items())}
