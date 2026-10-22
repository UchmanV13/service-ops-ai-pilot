"""Train scorers on dev only.

Calibration temperatures and the choice of production scorer come from
template-grouped out-of-fold (OOF) predictions on dev: each fold's predictions
are on phrasings the fold's model never saw, which mimics val and test. That
leaves val untouched for the threshold guarantee.

    python -m sopilot.train --pilot pilot2
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from scipy.sparse import hstack
from sklearn.metrics import average_precision_score

from .metrics import aurc
from .scorers import (Embedder, EmbedScorer, RulesScorer, TfidfScorer, model_text, softmax)
from .taxonomy import CRITICAL_INTENTS, INTENT_NAMES
from .textvec import Block, TfidfLinear

ROOT = Path(__file__).resolve().parents[2]
PILOTS = json.loads((ROOT / "config" / "pilots.json").read_text())
K = len(INTENT_NAMES)
IDX = {n: i for i, n in enumerate(INTENT_NAMES)}


def load(split):
    return [json.loads(line) for line in open(ROOT / "data" / "tickets" / f"{split}.jsonl", encoding="utf-8")]


def fit_tfidf(texts, y, C):
    vw = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=2)
    vc = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)
    X = hstack([vw.fit_transform(texts), vc.fit_transform(texts)]).tocsr()
    clf = LogisticRegression(C=C, max_iter=3000)
    clf.fit(X, y)
    coef = np.zeros((K, X.shape[1]))
    icpt = np.full(K, -30.0)  # classes absent from training get ~zero probability
    for j, c in enumerate(clf.classes_):
        coef[c] = clf.coef_[j]
        icpt[c] = clf.intercept_[j]
    blocks = [Block("word", (1, 2), {k: int(v) for k, v in vw.vocabulary_.items()}, vw.idf_),
              Block("char_wb", (2, 5), {k: int(v) for k, v in vc.vocabulary_.items()}, vc.idf_)]
    return TfidfLinear(blocks, coef, icpt, list(INTENT_NAMES))


def fit_embed(X, y, C):
    clf = LogisticRegression(C=C, max_iter=5000)
    clf.fit(X, y)
    coef = np.zeros((K, X.shape[1]))
    icpt = np.full(K, -30.0)
    for j, c in enumerate(clf.classes_):
        coef[c] = clf.coef_[j]
        icpt[c] = clf.intercept_[j]
    return coef, icpt


def fit_temperature(logits, y):
    def nll(logT):
        p = softmax(logits, np.exp(logT))
        return -np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)))
    res = minimize_scalar(nll, bounds=(-3, 3), method="bounded")
    return float(np.exp(res.x))


def nll(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def fit_binary_tfidf(texts, yb, C=8.0):
    vw = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=2)
    vc = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)
    X = hstack([vw.fit_transform(texts), vc.fit_transform(texts)]).tocsr()
    clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced").fit(X, yb)
    blocks = [Block("word", (1, 2), {k: int(v) for k, v in vw.vocabulary_.items()}, vw.idf_),
              Block("char_wb", (2, 5), {k: int(v) for k, v in vc.vocabulary_.items()}, vc.idf_)]
    return TfidfLinear(blocks, clf.coef_, clf.intercept_, ["critical"])


def fit_platt(z, yb):
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(np.asarray(z).reshape(-1, 1), yb)
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def main(pilot="pilot2"):
    t0 = time.time()
    cfg = PILOTS[pilot]
    ART = ROOT / "artifacts" / pilot
    ART.mkdir(parents=True, exist_ok=True)
    dev = [r for s in cfg["train"] for r in load(s)]
    texts = [model_text(r["text"]) for r in dev]
    y = np.array([IDX[r["gold"]["intent"]] for r in dev])
    groups = np.array([r["template_family"] for r in dev])
    gkf = GroupKFold(n_splits=5)
    folds = list(gkf.split(texts, y, groups))
    embedder = Embedder.from_wordllama()
    Xe = embedder.embed(texts).astype(np.float64)

    report = {"pilot": pilot, "train_splits": cfg["train"], "n_train": len(dev), "cv": "GroupKFold(5) by template family",
              "tfidf": {}, "embed": {}}

    # --- choose C by grouped OOF log loss, keep OOF logits for calibration
    best = {}
    for name, grid in (("tfidf", [2.0, 8.0, 32.0]), ("embed", [3.0, 30.0, 300.0])):
        for C in grid:
            oof = np.zeros((len(dev), K))
            for tr, te in folds:
                if name == "tfidf":
                    m = fit_tfidf([texts[i] for i in tr], y[tr], C)
                    oof[te] = m.logits([texts[i] for i in te])
                else:
                    coef, icpt = fit_embed(Xe[tr], y[tr], C)
                    oof[te] = Xe[te] @ coef.T + icpt
            T = fit_temperature(oof, y)
            p = softmax(oof, T)
            score = nll(p, y)
            report[name][f"C={C}"] = {"oof_nll_calibrated": round(score, 4), "T": round(T, 3),
                                      "oof_acc": round(float((p.argmax(1) == y).mean()), 4)}
            if name not in best or score < best[name][0]:
                best[name] = (score, C, T, oof)
        print(name, report[name])

    # --- rules: no training; temperature from dev
    rules = RulesScorer()
    rl = rules.logits(texts)
    rules.temperature = fit_temperature(rl, y)

    # --- OOF probabilities per scorer, ensemble, AURC for scorer choice
    p_t = softmax(best["tfidf"][3], best["tfidf"][2])
    p_e = softmax(best["embed"][3], best["embed"][2])
    p_ens_raw = (p_t + p_e) / 2
    T_ens = fit_temperature(np.log(np.clip(p_ens_raw, 1e-12, 1)), y)
    p_ens = softmax(np.log(np.clip(p_ens_raw, 1e-12, 1)), T_ens)
    p_r = softmax(rl, rules.temperature)
    choice = {}
    for name, p in (("rules", p_r), ("tfidf", p_t), ("embed", p_e), ("ensemble", p_ens)):
        err = (p.argmax(1) != y).astype(float)
        choice[name] = {"oof_acc": round(1 - err.mean(), 4), "aurc": round(aurc(p.max(1), err), 5),
                        "oof_nll": round(nll(p, y), 4)}
    chosen = min(("tfidf", "embed", "ensemble"), key=lambda k: choice[k]["aurc"])
    report["scorer_choice"] = {"by": "lowest AURC on grouped OOF dev predictions", "results": choice, "chosen": chosen}
    print(json.dumps(report["scorer_choice"], indent=1))

    # --- dedicated critical classifier (binary), grouped OOF + Platt scaling
    yb = np.array([int(r["gold"]["critical"]) for r in dev])
    oof_t = np.zeros(len(dev))
    oof_e = np.zeros(len(dev))
    for tr, te in folds:
        mt = fit_binary_tfidf([texts[i] for i in tr], yb[tr])
        oof_t[te] = mt.logits([texts[i] for i in te])[:, 0]
        ce = LogisticRegression(C=30.0, max_iter=5000, class_weight="balanced").fit(Xe[tr], yb[tr])
        oof_e[te] = Xe[te] @ ce.coef_[0] + ce.intercept_[0]
    pt_a, pt_b = fit_platt(oof_t, yb)
    pe_a, pe_b = fit_platt(oof_e, yb)
    p_bin_raw = (sigmoid(pt_a * oof_t + pt_b) + sigmoid(pe_a * oof_e + pe_b)) / 2
    pb_a, pb_b = fit_platt(np.log(p_bin_raw / (1 - p_bin_raw + 1e-12) + 1e-12), yb)
    p_bin = sigmoid(pb_a * np.log(p_bin_raw / (1 - p_bin_raw + 1e-12) + 1e-12) + pb_b)
    crit_idx = [INTENT_NAMES.index(c) for c in CRITICAL_INTENTS]
    p_sum = p_ens[:, crit_idx].sum(1)
    signals = {"intent_sum": p_sum, "binary": p_bin, "average": (p_sum + p_bin) / 2}
    ap = {k: round(float(average_precision_score(yb, v)), 4) for k, v in signals.items()}
    chosen_crit = max(ap, key=ap.get)
    report["critical_signal_choice"] = {"by": "average precision on grouped OOF train predictions", "ap": ap, "chosen": chosen_crit}
    print("critical signal:", report["critical_signal_choice"])
    mt = fit_binary_tfidf(texts, yb)
    ce = LogisticRegression(C=30.0, max_iter=5000, class_weight="balanced").fit(Xe, yb)
    crit_tf = TfidfScorer(mt, 1.0)
    crit_tf.save(ART / "critical_tfidf")
    np.savez_compressed(ART / "critical_embed.npz", coef=ce.coef_.astype(np.float32), intercept=ce.intercept_)
    (ART / "critical.json").write_text(json.dumps({"platt_tfidf": [pt_a, pt_b], "platt_embed": [pe_a, pe_b],
                                                   "platt_avg": [pb_a, pb_b], "chosen_signal": chosen_crit, "ap_oof": ap}))

    # --- final fits on all of the training data
    tf = TfidfScorer(fit_tfidf(texts, y, best["tfidf"][1]), best["tfidf"][2])
    tf.save(ART / "tfidf")
    coef, icpt = fit_embed(Xe, y, best["embed"][1])
    np.savez_compressed(ART / "embed_lr.npz", coef=coef.astype(np.float32), intercept=icpt, temperature=best["embed"][2])
    meta = {"pilot": pilot, "chosen_scorer": chosen, "T_ensemble": T_ens, "T_rules": rules.temperature,
            "C_tfidf": best["tfidf"][1], "C_embed": best["embed"][1], "intents": list(INTENT_NAMES),
            "trained_on": "+".join(cfg["train"]), "n_train": len(dev), "critical_signal": chosen_crit,
            "seconds": round(time.time() - t0, 1)}
    (ART / "meta.json").write_text(json.dumps(meta, indent=1))
    np.savez_compressed(ART / "oof_dev.npz", tfidf=p_t, embed=p_e, ensemble=p_ens, rules=p_r, y=y)
    (ROOT / "outputs" / pilot).mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / pilot / "train_report.json").write_text(json.dumps(report, indent=1))
    print("done", meta)


if __name__ == "__main__":
    import argparse
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--pilot", default="pilot2")
    main(ap_.parse_args().pilot)
