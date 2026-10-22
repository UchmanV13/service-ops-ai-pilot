"""Step 2-3 of the charter protocol, on the validation split only.

For every scorer arm: choose the critical threshold, then the automation
threshold by Learn-then-Test, then apply the pre-set non-English rule.
Writes outputs/thresholds.json, which is committed before the test split is scored.

    python scripts/set_thresholds.py --pilot pilot2
"""
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sopilot.evaluation import (by_language, choose_auto_threshold_ltt, choose_critical_threshold, load,  # noqa: E402
                                run_policy, summarize)
from sopilot.pipeline import Params, Pipeline  # noqa: E402
from sopilot.scorers import Embedder  # noqa: E402

PILOTS = json.loads((ROOT / "config" / "pilots.json").read_text())


def main(pilot):
    cfg = PILOTS[pilot]
    ALPHA, DELTA = cfg["alpha"], cfg["delta"]
    art = ROOT / "artifacts" / pilot
    meta = json.loads((art / "meta.json").read_text())
    pp = dict(cfg["params"])
    if pp.get("critical_signal") == "chosen_on_oof":
        pp["critical_signal"] = meta.get("critical_signal", "intent_sum")
    val = load(cfg["calibrate"])
    texts = [r["text"] for r in val]
    emb = Embedder.from_wordllama()
    import math
    out = {"pilot": pilot, "protocol": {"alpha": ALPHA, "delta": DELTA, "critical_lower_bound_target": 0.95,
                                        "n_min_automated": math.ceil(math.log(DELTA) / math.log(1 - ALPHA)),
                                        "split": cfg["calibrate"], "n": len(val)}, "arms": {}}
    for arm in ("rules", "tfidf", "embed", "ensemble"):
        pipe = Pipeline.load(art=art, scorer_name=arm, embedder=emb)
        evs = pipe.analyze(texts)
        signal = pp["critical_signal"] if pipe.critical is not None else "intent_sum"
        tau, ctrace = choose_critical_threshold(val, evs, signal=signal)
        base = Params(critical_threshold=tau if tau is not None else 0.0, multi_mode=pp["multi_mode"],
                      multi_threshold=pp["multi_threshold"], sibling_guard=pp["sibling_guard"],
                      critical_signal=signal, version=f"{pilot}-policy")
        lam, ltrace = choose_auto_threshold_ltt(val, evs, base, alpha=ALPHA, delta=DELTA)
        params = replace(base, auto_threshold=lam if lam is not None else 1.01)
        # Pre-set rule: if non-English automated tickets on val have an error rate above alpha, send them to people.
        _, outs = run_policy(val, evs, params)
        langs = by_language(outs)
        ne = [o for o in outs if o["language"] != "en" and o["auto"]]
        ne_err = (sum(o["auto_error"] for o in ne) / len(ne)) if ne else 0.0
        if ne and ne_err > ALPHA:
            params = replace(params, non_english="review")
        _, outs = run_policy(val, evs, params)
        out["arms"][arm] = {
            "params": asdict(params), "critical_threshold_trace": ctrace[:40], "ltt_trace": ltrace,
            "non_english_rule": {"n_auto": len(ne), "error_rate": ne_err, "policy": params.non_english},
            "val_summary": summarize(outs, bootstrap=False), "val_by_language": langs,
            "lambda_found": lam is not None, "tau_found": tau is not None,
        }
        s = out["arms"][arm]["val_summary"]
        print(f"{arm:9s} tau_c={tau} lambda={lam} non_en={params.non_english} | val coverage="
              f"{s['automated_coverage']['rate']:.3f} auto_acc={s['automated_accuracy']['rate'] or 0:.3f} "
              f"crit_recall={s['critical_recall']['rate']:.3f}")
    (ROOT / "outputs" / pilot).mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / pilot / "thresholds.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="pilot2")
    main(ap.parse_args().pilot)
