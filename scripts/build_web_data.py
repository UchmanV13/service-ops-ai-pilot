"""Build the web app's data files from the frozen pipeline and the evaluation outputs.

  web/public/results_summary.json  dashboard numbers for both pilots
  web/public/replay.json           curated held-out tickets with the real pipeline's
                                   decisions under the frozen and exploratory policies

    python scripts/build_web_data.py
"""
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "api"))

from sopilot.evaluation import load, outcome  # noqa: E402
from sopilot.pipeline import Params, Pipeline, decide  # noqa: E402
from sopilot.taxonomy import AUTOMATED_ACTIONS as AUTOMATED  # noqa: E402

PUB = ROOT / "web" / "public"


def pick(rows, decs_x, pred, k):
    out = []
    for r, d in zip(rows, decs_x):
        if pred(r, d) and len(out) < k:
            out.append(r)
    return out


def summary():
    p1 = json.loads((ROOT / "outputs" / "pilot1" / "results.json").read_text())
    p2 = json.loads((ROOT / "outputs" / "pilot2" / "results.json").read_text())
    t1 = json.loads((ROOT / "outputs" / "pilot1" / "thresholds.json").read_text())
    t2 = json.loads((ROOT / "outputs" / "pilot2" / "thresholds.json").read_text())

    def core(res, split):
        s = res["arms"]["ensemble"][split]
        keep = ("automated_coverage", "automated_accuracy", "inappropriate_automation", "critical_recall",
                "escalation_precision", "routing_accuracy", "intent_accuracy", "human_workload")
        return {k: {"rate": s[k]["rate"], "k": s[k]["k"], "n": s[k]["n"], "ci95": s[k]["ci95"]} for k in keep} | {
            "n": s["n"], "latency_ms": s.get("latency_ms")}

    def arms(res, split):
        return {a: {k: res["arms"][a][split][k]["rate"] for k in ("automated_coverage", "automated_accuracy", "critical_recall",
                                                                    "escalation_precision", "routing_accuracy", "intent_accuracy")}
                for a in res["arms"]}

    def ltt(th):
        tr = th["arms"]["ensemble"]["ltt_trace"]
        return [x for x in tr if not x.get("skipped")][:25]

    pilots = []
    for name, res, th, hold, shift, cal in (("Pilot 1", p1, t1, "test", "shift", "val (v2)"),
                                            ("Pilot 2", p2, t2, "holdout_v2", "shift_v2", "Pilot 1 test")):
        pilots.append({
            "name": name, "holdout": hold, "calibration_split": cal, "decision": res["go_no_go"]["decision"],
            "go_no_go": {k: v for k, v in res["go_no_go"].items() if k.startswith("G")},
            "params": th["arms"]["ensemble"]["params"], "alpha": th["protocol"]["alpha"],
            "holdout_metrics": core(res, hold), "shift_metrics": core(res, shift), "handwritten_metrics": core(res, "handwritten"),
            "arms": arms(res, hold), "economics": {k: res["economics"][k] for k in ("test_base", "test_pessimistic")},
            "tornado": res["economics"]["tornado"], "threshold_sweep": res["threshold_sweep"][hold],
            "critical_sweep": res.get("critical_sweep_holdout") or res.get("critical_sweep_test"),
            "ablations": res.get("ablations_holdout") or res.get("ablations_test"),
            "components": res["components"][hold], "retrieval": res.get("retrieval_holdout_en") or res.get("retrieval_test_en"),
            "robustness": res.get("robustness_holdout") or res.get("robustness_test"),
            "calibration": {k: {"ece": v["ece"], "reliability": v["reliability"]} for k, v in res["calibration"].items()},
            "by_language": res["by_language"][hold], "ltt_trace": ltt(th),
        })
    lc = json.loads((ROOT / "outputs" / "learning_curve.json").read_text())
    return {"pilots": pilots, "learning_curve": lc,
            "note": "Synthetic tickets for a fictional vendor (Halden Devices). Cost inputs are illustrative assumptions."}


def main():
    PUB.mkdir(parents=True, exist_ok=True)
    (PUB / "results_summary.json").write_text(json.dumps(summary(), default=float))

    from app import load_policies  # noqa: E402
    pol = load_policies()
    pipe = Pipeline.load(art=ROOT / "artifacts" / "pilot2")
    hold, hand = load("holdout_v2"), load("handwritten")
    ev_h = pipe.analyze([r["text"] for r in hold])
    dx = [decide(e, pol["exploratory"]) for e in ev_h]
    g = lambda r: r["gold"]  # noqa: E731
    chosen = []
    cats = [
        ("Routine how-to, answered from the knowledge base", lambda r, d: d["action"] == "AUTO_REPLY_KB" and g(r)["action"] == "AUTO_REPLY_KB" and r["language"] == "en", 3),
        ("Status lookup (read-only)", lambda r, d: d["action"] == "AUTO_LOOKUP" and g(r)["action"] == "AUTO_LOOKUP", 3),
        ("Self-scheduling link", lambda r, d: d["action"] == "AUTO_SCHEDULE_LINK" and g(r)["action"] == "AUTO_SCHEDULE_LINK", 1),
        ("Missing identifier", lambda r, d: d["action"] == "REQUEST_INFO" and g(r)["action"] == "REQUEST_INFO", 2),
        ("Safety: battery", lambda r, d: g(r)["intent"] == "battery_safety", 2),
        ("Enterprise outage", lambda r, d: g(r)["intent"] == "enterprise_outage", 1),
        ("Data loss", lambda r, d: g(r)["intent"] == "data_loss", 1),
        ("Legal threat", lambda r, d: g(r)["intent"] == "legal_threat", 1),
        ("Prompt injection inside the ticket", lambda r, d: r["flags"]["injection"], 2),
        ("Two requests in one ticket", lambda r, d: r["flags"]["multi_issue"], 2),
        ("Look-alike request that needs a person", lambda r, d: g(r)["intent"] in ("ownership_transfer", "warranty_extension"), 2),
        ("Hardware repair (never automated)", lambda r, d: g(r)["intent"] in ("no_power", "screen_damage"), 2),
        ("Non-English", lambda r, d: r["language"] != "en", 3),
        ("Model error the policy caught", lambda r, d: d["intent"] != g(r)["intent"] and not d["automated"] and not g(r)["critical"], 2),
    ]
    seen = set()
    for label, f, k in cats:
        n = 0
        for r, d in zip(hold, dx):
            if n < k and r["id"] not in seen and f(r, d):
                chosen.append((label, r))
                seen.add(r["id"])
                n += 1
    for r in hand[:60:5]:
        chosen.append(("Hand-written ticket", r))
    tickets = []
    texts = [r["text"] for _, r in chosen]
    evs = pipe.analyze(texts)
    for (label, r), e in zip(chosen, evs):
        dec = {}
        for name, p in pol.items():
            d = decide(e, p, pipe.retriever, model_version=pipe.model_version)
            d["latency_ms"] = round(e["latency_ms"], 2)
            o = outcome(r, d)
            dec[name] = d | {"correct": bool(o["action_ok"] and o["intent_ok"]) if not d["action"] == "ESCALATE" else bool(o["critical"]),
                             "outcome": "inappropriate automation" if o["inappropriate"] else "wrong automation" if o["wrong_auto"]
                             else "correct automation" if o["correct_auto"] else "correct escalation" if (o["critical"] and o["escalated"]) else "missed critical" if (o["critical"] and not o["escalated"])
                             else "false escalation" if (o["escalated"] and not o["critical"])
                             else "could have been automated" if r["gold"]["action"] in AUTOMATED else "sent to a person"}
        tickets.append({"id": r["id"], "label": label, "text": r["text"], "language": r["language"], "gold": r["gold"],
                        "flags": {k: v for k, v in r["flags"].items() if v}, "decisions": dec})
    replay = {"model_version": pipe.model_version,
              "policies": {k: asdict(v) | {"certified": k == "frozen"} for k, v in pol.items()},
              "tickets": tickets}
    (PUB / "replay.json").write_text(json.dumps(replay, default=float, ensure_ascii=False))
    print("replay tickets:", len(tickets), "| summary + replay written to web/public/")


if __name__ == "__main__":
    main()
