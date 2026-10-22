"""Train scorers on dev only.

Calibration temperatures and the choice of production scorer come from
template-grouped out-of-fold (OOF) predictions on dev: each fold's predictions
are on phrasings the fold's model never saw, which mimics val and test. That
leaves val untouched for the threshold guarantee.

    python -m sopilot.train
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

from .metrics import aurc
from .scorers import (Embedder, EmbedScorer, RulesScorer, TfidfScorer, model_text, softmax)
from .taxonomy import INTENT_NAMES
from .textvec import Block, TfidfLinear

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
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


def main():
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    dev = load("dev")
    texts = [model_text(r["text"]) for r in dev]
    y = np.array([IDX[r["gold"]["intent"]] for r in dev])
    groups = np.array([r["template_family"] for r in dev])
    gkf = GroupKFold(n_splits=5)
    folds = list(gkf.split(texts, y, groups))
    embedder = Embedder.from_wordllama()
    Xe = embedder.embed(texts).astype(np.float64)

    report = {"n_dev": len(dev), "cv": "GroupKFold(5) by template family", "tfidf": {}, "embed": {}}

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

    # --- final fits on all of dev
    tf = TfidfScorer(fit_tfidf(texts, y, best["tfidf"][1]), best["tfidf"][2])
    tf.save(ART / "tfidf")
    coef, icpt = fit_embed(Xe, y, best["embed"][1])
    np.savez_compressed(ART / "embed_lr.npz", coef=coef.astype(np.float32), intercept=icpt, temperature=best["embed"][2])
    meta = {"chosen_scorer": chosen, "T_ensemble": T_ens, "T_rules": rules.temperature,
            "C_tfidf": best["tfidf"][1], "C_embed": best["embed"][1], "intents": list(INTENT_NAMES),
            "trained_on": "dev", "n_train": len(dev), "seconds": round(time.time() - t0, 1)}
    (ART / "meta.json").write_text(json.dumps(meta, indent=1))
    np.savez_compressed(ART / "oof_dev.npz", tfidf=p_t, embed=p_e, ensemble=p_ens, rules=p_r, y=y)
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "train_report.json").write_text(json.dumps(report, indent=1))
    print("done", meta)


if __name__ == "__main__":
    main()
