"""Score every arm once on test, shift, hand-written and paraphrase sets with the
thresholds frozen in outputs/thresholds.json, plus ablations, robustness,
calibration, retrieval, learning curve and economics.

    python scripts/run_eval.py
"""
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sopilot import economics as econ  # noqa: E402
from sopilot.evaluation import by_language, load, outcome, per_intent, run_policy, summarize  # noqa: E402
from sopilot.generate import typo  # noqa: E402
from sopilot.guards import detect_injection, hard_escalation, redact_pii  # noqa: E402
from sopilot.metrics import aurc, clopper_pearson, ece, risk_coverage  # noqa: E402
from sopilot.pipeline import Params, Pipeline, decide, multi_request  # noqa: E402
from sopilot.retrieval import Retriever  # noqa: E402
from sopilot.scorers import Embedder, model_text, softmax  # noqa: E402
from sopilot.taxonomy import AUTOMATED_ACTIONS, INTENT_NAMES, INTENTS  # noqa: E402
from sopilot.templates_ml import INJECTIONS  # noqa: E402

OUT = ROOT / "outputs"
ARMS = ("rules", "tfidf", "embed", "ensemble")
SPLITS = ("test", "shift", "handwritten")


def params_for(th, arm):
    p = th["arms"][arm]["params"]
    return Params(**{k: p[k] for k in ("auto_threshold", "critical_threshold", "multi_threshold", "non_english",
                                       "require_evidence", "version")})


def go_no_go(test, shift, econ_base, econ_pess):
    g = {
        "G1_critical_recall": {"value": test["critical_recall"]["rate"], "lower95": test["critical_recall"]["lower95_one_sided"],
                               "pass": test["critical_recall"]["rate"] >= 0.98 and test["critical_recall"]["lower95_one_sided"] >= 0.95},
        "G2_inappropriate_automation": {"value": test["inappropriate_automation"]["rate"],
                                        "upper95": test["inappropriate_automation"]["upper95_one_sided"],
                                        "pass": (test["inappropriate_automation"]["rate"] or 0) <= 0.02
                                        and (test["inappropriate_automation"]["upper95_one_sided"] or 1) <= 0.03},
        "G3_automated_accuracy": {"value": test["automated_accuracy"]["rate"], "pass": (test["automated_accuracy"]["rate"] or 0) >= 0.95},
        "G4_automated_coverage": {"value": test["automated_coverage"]["rate"], "pass": test["automated_coverage"]["rate"] >= 0.30},
        "G5_routing_accuracy": {"value": test["routing_accuracy"]["rate"], "pass": test["routing_accuracy"]["rate"] >= 0.85},
        "G6_shift": {"critical_recall": shift["critical_recall"]["rate"], "inappropriate": shift["inappropriate_automation"]["rate"],
                     "pass": shift["critical_recall"]["rate"] >= 0.95 and (shift["inappropriate_automation"]["rate"] or 0) <= 0.05},
        "G7_economics": {"base": econ_base["net_usd_per_1000"], "pessimistic": econ_pess["net_usd_per_1000"],
                         "pass": econ_base["net_usd_per_1000"] > 0 and econ_pess["net_usd_per_1000"] > 0},
    }
    allp = all(v["pass"] for v in g.values())
    core = g["G1_critical_recall"]["pass"] and g["G2_inappropriate_automation"]["pass"]
    g["decision"] = "GO" if allp else ("NARROW GO" if core else "NO-GO")
    g["failed"] = [k for k, v in g.items() if isinstance(v, dict) and not v["pass"]]
    return g


def main():
    t_start = time.time()
    th = json.loads((OUT / "thresholds.json").read_text())
    cfg = econ.load_config()
    emb = Embedder.from_wordllama()
    data = {s: load(s) for s in SPLITS + ("paraphrase", "dev", "val")}
    R = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "data_note": "Synthetic tickets for a fictional vendor; labels from the labeling guide.",
         "thresholds": {a: th["arms"][a]["params"] for a in ARMS}, "arms": {}}
    pipes, evs = {}, {}

    # ------------------------------------------------------------ all arms, all splits
    for arm in ARMS:
        pipes[arm] = Pipeline.load(scorer_name=arm, embedder=emb)
        prm = params_for(th, arm)
        R["arms"][arm] = {}
        for s in SPLITS + ("paraphrase",):
            ev = pipes[arm].analyze([r["text"] for r in data[s]])
            evs[(arm, s)] = ev
            decs, outs = run_policy(data[s], ev, prm)
            R["arms"][arm][s] = summarize(outs, [e["latency_ms"] for e in ev], bootstrap=(s == "test"))
            if arm == "ensemble":
                R.setdefault("ensemble_outs", {})[s] = outs
        print(arm, "test coverage", round(R["arms"][arm]["test"]["automated_coverage"]["rate"], 3),
              "auto acc", R["arms"][arm]["test"]["automated_accuracy"]["rate"],
              "crit", round(R["arms"][arm]["test"]["critical_recall"]["rate"], 3))

    # all-human baseline
    base_outs = [outcome(r, {"action": "HUMAN_REVIEW", "intent": "none", "queue": "none"}) for r in data["test"]]
    R["all_human_baseline"] = {"test": summarize(base_outs, bootstrap=False)}

    prod = "ensemble"
    P = params_for(th, prod)
    outs_test = R["ensemble_outs"]["test"]
    outs_shift = R["ensemble_outs"]["shift"]

    # ------------------------------------------------------------ economics + go/no-go
    e_base = econ.net_value(outs_test, cfg["base"])
    e_pess = econ.net_value(outs_test, econ.pessimistic(cfg["base"], cfg["pessimistic_multipliers"]))
    R["economics"] = {
        "test_base": e_base, "test_pessimistic": e_pess, "shift_base": econ.net_value(outs_shift, cfg["base"]),
        "tornado": econ.tornado(outs_test, cfg["base"]),
        "break_even_missed_critical_usd": econ.break_even_missed_critical(outs_test, cfg["base"]),
        "assumptions": cfg,
    }
    R["go_no_go"] = go_no_go(R["arms"][prod]["test"], R["arms"][prod]["shift"], e_base, e_pess)
    print("GO/NO-GO:", R["go_no_go"]["decision"], R["go_no_go"]["failed"])

    # ------------------------------------------------------------ per-intent, language, narrow scope
    R["per_intent_test"] = per_intent(outs_test)
    R["by_language"] = {s: by_language(R["ensemble_outs"][s]) for s in SPLITS}

    # ------------------------------------------------------------ risk-coverage / calibration (intent level)
    R["risk_coverage"], R["calibration"] = {}, {}
    y = np.array([INTENT_NAMES.index(r["gold"]["intent"]) for r in data["test"]])
    for arm in ARMS:
        P_ = np.array([e["probs"] for e in evs[(arm, "test")]])
        err = (P_.argmax(1) != y).astype(float)
        R["risk_coverage"][arm] = {"aurc": aurc(P_.max(1), err), "intent_accuracy": float(1 - err.mean()),
                                   "curve": risk_coverage(P_.max(1), err, 40)}
        e_, tab = ece(P_.max(1), 1 - err)
        R["calibration"][arm] = {"ece": e_, "reliability": tab}
    # uncalibrated ensemble (T = 1 everywhere) for comparison
    sc = pipes["ensemble"].scorer
    mt = [model_text(r["text"]) for r in data["test"]]
    raw = np.mean([softmax(m.logits(mt), 1.0) for m in sc.members], axis=0)
    e_raw, tab_raw = ece(raw.max(1), (raw.argmax(1) == y).astype(float))
    R["calibration"]["ensemble_uncalibrated"] = {"ece": e_raw, "reliability": tab_raw}

    # ------------------------------------------------------------ automation threshold sweep (dashboard slider)
    sweep = {}
    for s in ("val", "test", "shift"):
        ev = evs.get((prod, s)) or pipes[prod].analyze([r["text"] for r in data[s]])
        evs[(prod, s)] = ev
        pts = []
        for lam in np.round(np.arange(0.50, 1.0, 0.005), 3):
            _, o = run_policy(data[s], ev, replace(P, auto_threshold=float(lam)))
            sm = summarize(o, bootstrap=False)
            pts.append({"lambda": float(lam), "coverage": sm["automated_coverage"]["rate"],
                        "auto_error": 1 - sm["automated_accuracy"]["rate"] if sm["automated_accuracy"]["rate"] is not None else None,
                        "inappropriate": sm["inappropriate_automation"]["rate"], "n_auto": sm["automated_coverage"]["k"],
                        "workload": sm["human_workload"]["rate"],
                        "net_usd_per_1000": econ.net_value(o, cfg["base"])["net_usd_per_1000"]})
        sweep[s] = pts
    R["threshold_sweep"] = sweep
    # critical threshold sweep on test (recall vs precision vs workload)
    csw = []
    for tau in [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 0.9, 1.01]:
        _, o = run_policy(data["test"], evs[(prod, "test")], replace(P, critical_threshold=tau))
        sm = summarize(o, bootstrap=False)
        csw.append({"tau": tau, "critical_recall": sm["critical_recall"]["rate"], "escalation_precision": sm["escalation_precision"]["rate"],
                    "escalated_share": sum(x["escalated"] for x in o) / len(o)})
    R["critical_sweep_test"] = csw

    # ------------------------------------------------------------ ablations (test, production arm)
    ab = {}
    ev = evs[(prod, "test")]

    def run_variant(name, evs_mod, prm):
        _, o = run_policy(data["test"], evs_mod, prm)
        sm = summarize(o, bootstrap=False)
        ab[name] = {k: sm[k]["rate"] for k in ("automated_coverage", "automated_accuracy", "inappropriate_automation",
                                                 "critical_recall", "escalation_precision", "routing_accuracy")}
        ab[name]["net_usd_per_1000"] = econ.net_value(o, cfg["base"])["net_usd_per_1000"]

    run_variant("full_system", ev, P)
    run_variant("no_hard_rules", [dict(e, guard_hits=[]) for e in ev], P)
    run_variant("no_critical_model", ev, replace(P, critical_threshold=1.01))
    run_variant("no_injection_detector", [dict(e, injection=[]) for e in ev], P)
    run_variant("no_multi_request_detector", ev, replace(P, multi_threshold=1.01))
    run_variant("no_evidence_check", ev, replace(P, require_evidence=False))
    run_variant("non_english_to_humans", ev, replace(P, non_english="review"))
    run_variant("threshold_0.80_no_guarantee", ev, replace(P, auto_threshold=0.80))
    R["ablations_test"] = ab

    # ------------------------------------------------------------ component diagnostics
    def guard_stats(rows):
        crit = [r for r in rows if r["gold"]["critical"]]
        non = [r for r in rows if not r["gold"]["critical"]]
        hit = sum(bool(hard_escalation(redact_pii(r["text"])[0])) for r in crit)
        fp = sum(bool(hard_escalation(redact_pii(r["text"])[0])) for r in non)
        return {"critical_n": len(crit), "caught": hit, "recall": hit / len(crit) if crit else None,
                "false_positives": fp, "fp_rate": fp / len(non) if non else None}

    def inj_stats(rows):
        pos = [r for r in rows if r["flags"]["injection"]]
        neg = [r for r in rows if not r["flags"]["injection"]]
        tp = sum(bool(detect_injection(r["text"])) for r in pos)
        fp = sum(bool(detect_injection(r["text"])) for r in neg)
        return {"n_injection": len(pos), "detected": tp, "false_positives": fp}

    def multi_stats(rows, ev):
        pos = [(r, e) for r, e in zip(rows, ev) if r["flags"]["multi_issue"]]
        neg = [(r, e) for r, e in zip(rows, ev) if not r["flags"]["multi_issue"]]
        tp = sum(bool(multi_request(e, P.multi_threshold)) for r, e in pos)
        fp = sum(bool(multi_request(e, P.multi_threshold)) for r, e in neg)
        return {"n_multi": len(pos), "detected": tp, "recall": tp / len(pos) if pos else None, "false_positives": fp,
                "fp_rate": fp / len(neg) if neg else None}

    R["components"] = {s: {"hard_rules": guard_stats(data[s]), "injection": inj_stats(data[s]),
                           "multi_request": multi_stats(data[s], evs[(prod, s)])} for s in SPLITS}
    R["components"]["dev_hard_rules_in_sample"] = guard_stats(data["dev"])
    # language id
    from sopilot.extract import detect_language
    for s in SPLITS:
        rows = data[s]
        R["components"][s]["language_id_accuracy"] = float(np.mean([detect_language(r["text"]) == r["language"] for r in rows]))
    # field extraction
    from sopilot.extract import extract_fields
    tot = ok = 0
    for r in data["test"] + data["shift"]:
        f = extract_fields(r["text"])
        gold = {k: (v.upper() if k == "service_tag" else ("ORD-" + v[-8:] if k == "order_number" else "CS-" + v[-7:])) for k, v in r["fields"].items()}
        tot += 1
        ok += f == gold
    R["components"]["field_extraction_exact_match_test_shift"] = ok / tot
    # PII
    pii_rows = [r for r in data["test"] if r["flags"]["pii"]]
    leaks = 0
    for r in pii_rows:
        red, _ = redact_pii(r["text"])
        leaks += ("@example.com" in red) or ("4111" in red)
    R["components"]["pii_test"] = {"tickets_with_pii": len(pii_rows), "email_or_card_leaks_after_redaction": leaks}

    # retrieval
    arts = json.loads((ROOT / "data" / "kb" / "articles.json").read_text(encoding="utf-8"))
    rets = {"bm25": Retriever(arts), "hybrid": Retriever(arts, emb)}
    rr = {}
    for name, ret in rets.items():
        rows = [r for r in data["test"] if r["gold"]["kb"] and r["language"] == "en"]
        h1 = h3 = 0
        for r in rows:
            got = [x["id"] for x in ret.search(redact_pii(r["text"])[0], 3)]
            h1 += got[0] in r["gold"]["kb"]
            h3 += any(g in r["gold"]["kb"] for g in got)
        rr[name] = {"n": len(rows), "recall_at_1": h1 / len(rows), "recall_at_3": h3 / len(rows)}
    R["retrieval_test_en"] = rr

    # ------------------------------------------------------------ robustness (test, production arm)
    rng = random.Random(11)
    rob = {}
    variants = {
        "typos_6pct": [typo(r["text"], rng, 0.06) for r in data["test"]],
        "lowercase": [r["text"].lower() for r in data["test"]],
    }
    for name, texts in variants.items():
        evv = pipes[prod].analyze(texts)
        _, o = run_policy(data["test"], evv, P)
        sm = summarize(o, bootstrap=False)
        rob[name] = {k: sm[k]["rate"] for k in ("automated_coverage", "automated_accuracy", "inappropriate_automation", "critical_recall")}
    # injection appended to tickets the system automated
    decs, _ = run_policy(data["test"], evs[(prod, "test")], P)
    auto_rows = [r for r, d in zip(data["test"], decs) if d["automated"]]
    inj_texts = [r["text"] + "\n" + rng.choice(INJECTIONS) for r in auto_rows]
    evv = pipes[prod].analyze(inj_texts)
    still = sum(decide(e, P)["automated"] for e in evv)
    rob["injection_appended_to_automated_tickets"] = {"n": len(auto_rows), "still_automated": still}
    # paraphrase stability: same case, 6 different test phrasings
    pev = evs[(prod, "paraphrase")]
    groups = {}
    for r, e in zip(data["paraphrase"], pev):
        groups.setdefault(r["group"], []).append(decide(e, P))
    same_action = np.mean([len({d["action"] for d in g}) == 1 for g in groups.values()])
    same_intent = np.mean([len({d["intent"] for d in g}) == 1 for g in groups.values()])
    pair_agree = []
    for g in groups.values():
        acts = [d["action"] for d in g]
        pair_agree += [acts[i] == acts[j] for i in range(len(acts)) for j in range(i + 1, len(acts))]
    rob["paraphrase"] = {"groups": len(groups), "variants_per_group": 6, "all_same_action": float(same_action),
                         "all_same_intent": float(same_intent), "pairwise_action_agreement": float(np.mean(pair_agree))}
    R["robustness_test"] = rob

    # ------------------------------------------------------------ single-ticket latency
    lat = []
    for r in data["test"][:200]:
        t0 = time.perf_counter()
        pipes[prod].triage(r["text"], P)
        lat.append((time.perf_counter() - t0) * 1000)
    R["latency_single_ticket_ms"] = {"p50": float(np.percentile(lat, 50)), "p95": float(np.percentile(lat, 95)),
                                     "hardware": "2 vCPU cloud container, no GPU", "cost_per_ticket_usd": "~0 marginal (CPU only); infra in maintenance line"}

    # ------------------------------------------------------------ examples for the readout / dashboard
    ex = []
    pick = {"correct_auto": 3, "inappropriate": 3, "wrong_auto": 3, "missed_critical": 3, "false_escalation": 2}
    decs_test, _ = run_policy(data["test"], evs[(prod, "test")], P)
    for r, d, o in zip(data["test"], decs_test, outs_test):
        kind = ("correct_auto" if o["correct_auto"] else "inappropriate" if o["inappropriate"] else "wrong_auto" if o["wrong_auto"]
                else "missed_critical" if (o["critical"] and not o["escalated"]) else "false_escalation" if (o["escalated"] and not o["critical"]) else None)
        if kind and pick.get(kind, 0) > 0:
            pick[kind] -= 1
            ex.append({"kind": kind, "id": r["id"], "text": redact_pii(r["text"])[0], "gold_intent": r["gold"]["intent"],
                       "gold_action": r["gold"]["action"], "pred_intent": d["intent"], "pred_action": d["action"],
                       "confidence": d["confidence"], "reasons": d["reasons"]})
    R["examples_test"] = ex

    R.pop("ensemble_outs")
    R["seconds"] = round(time.time() - t_start, 1)
    (OUT / "results.json").write_text(json.dumps(R, indent=1, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x)))
    print("wrote outputs/results.json in", R["seconds"], "s")


if __name__ == "__main__":
    main()
