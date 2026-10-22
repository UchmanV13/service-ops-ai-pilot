"""Claude arm under the Pilot 2 protocol (needs ANTHROPIC_API_KEY; not run in the build session).

Same guards, policy, threshold protocol and go/no-go criteria as the other arms:
thresholds on the calibration split (Pilot 1 test), scored once on holdout_v2.
Model names and prices change; pass the ones you use, from the provider's docs.

    export ANTHROPIC_API_KEY=...
    python scripts/run_llm_eval.py --model <model-id> --price-in <USD per M input tokens> --price-out <USD per M output tokens>
    python scripts/run_llm_eval.py ... --limit 100      # cheap dry run on 100 tickets per split

Writes outputs/pilot3_llm/{thresholds,results}.json. Responses are cached in outputs/cache/llm/.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sopilot import economics as econ  # noqa: E402
from sopilot.evaluation import (choose_auto_threshold_ltt, choose_critical_threshold, load, run_policy,  # noqa: E402
                                summarize)
from sopilot.llm import ClaudeTriage, LLMScorer  # noqa: E402
from sopilot.pipeline import Params, Pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--price-in", type=float, required=True)
    ap.add_argument("--price-out", type=float, required=True)
    ap.add_argument("--samples", type=int, default=5, help="answers per ticket for the self-consistency signal")
    ap.add_argument("--mode", choices=["vote", "verbalized"], default="vote")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config" / "pilots.json").read_text())["pilot2"]
    base_pipe = Pipeline.load(art=ROOT / "artifacts" / "pilot2")
    triage = ClaudeTriage(a.model, a.price_in, a.price_out, base_pipe.retriever, samples=a.samples)
    pipe = Pipeline(LLMScorer(triage, a.mode), base_pipe.retriever, f"claude-{a.model}-{a.mode}",
                    sentence_scorer=base_pipe.scorer)
    out = ROOT / "outputs" / "pilot3_llm"
    out.mkdir(parents=True, exist_ok=True)

    cal = load(cfg["calibrate"])
    hold = load(cfg["holdout"])
    if a.limit:
        cal, hold = cal[:a.limit], hold[:a.limit]
    t0 = time.time()
    ev_cal = pipe.analyze([r["text"] for r in cal])
    tau, _ = choose_critical_threshold(cal, ev_cal)
    pp = cfg["params"]
    base = Params(critical_threshold=tau if tau is not None else 0.0, multi_mode=pp["multi_mode"], multi_threshold=pp["multi_threshold"],
                  sibling_guard=pp["sibling_guard"], critical_signal="intent_sum", version="pilot3-llm-policy")
    lam, trace = choose_auto_threshold_ltt(cal, ev_cal, base, alpha=cfg["alpha"], delta=cfg["delta"])
    P = replace(base, auto_threshold=lam if lam is not None else 1.01)
    (out / "thresholds.json").write_text(json.dumps({"params": asdict(P), "ltt_trace": trace, "tau": tau}, indent=1, default=float))
    cost_cal = triage.cost_usd()

    ev_hold = pipe.analyze([r["text"] for r in hold])
    _, outs = run_policy(hold, ev_hold, P)
    s = summarize(outs, [e["latency_ms"] for e in ev_hold])
    eco = econ.load_config()
    e_base = econ.net_value(outs, eco["base"])
    per_ticket = (triage.cost_usd() - cost_cal) / max(1, len(hold))
    e_base["llm_usd_per_1000"] = round(per_ticket * 1000, 2)
    e_base["net_usd_per_1000"] = round(e_base["net_usd_per_1000"] - per_ticket * 1000, 2)
    res = {"model": a.model, "mode": a.mode, "samples": a.samples, "n_calibration": len(cal), "n_holdout": len(hold),
           "params": asdict(P), "holdout": s, "economics_base": e_base, "usage": triage.usage,
           "llm_cost_usd_total": round(triage.cost_usd(), 4), "seconds": round(time.time() - t0, 1)}
    (out / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("model", "n_holdout", "llm_cost_usd_total")}, indent=1))
    print("coverage", s["automated_coverage"]["rate"], "auto acc", s["automated_accuracy"]["rate"],
          "critical recall", s["critical_recall"]["rate"], "net/1000", e_base["net_usd_per_1000"])


if __name__ == "__main__":
    main()
