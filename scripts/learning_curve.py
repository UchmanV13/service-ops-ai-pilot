"""How much labeled phrasing variety does the intent model need?

Trains the TF-IDF + embedding ensemble on dev+val restricted to k phrasing
families per intent (k = 3, 6, 10, 14, 18) and scores intent accuracy and AURC on
the Pilot 2 holdout. Descriptive only: no threshold or decision depends on it.

    python scripts/learning_curve.py
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sopilot.evaluation import load  # noqa: E402
from sopilot.metrics import aurc  # noqa: E402
from sopilot.scorers import Embedder, model_text, softmax  # noqa: E402
from sopilot.taxonomy import INTENT_NAMES  # noqa: E402
from sopilot.train import fit_embed, fit_tfidf  # noqa: E402


def main():
    train = load("dev") + load("val")
    hold = load("holdout_v2")
    emb = Embedder.from_wordllama()
    fams = defaultdict(set)
    for r in train:
        if r["language"] == "en":
            fams[r["gold"]["intent"]].add(r["template_family"])
    rng = random.Random(3)
    order = {k: rng.sample(sorted(v), len(v)) for k, v in fams.items()}
    ht = [model_text(r["text"]) for r in hold]
    He = emb.embed(ht).astype(float)
    y_h = np.array([INTENT_NAMES.index(r["gold"]["intent"]) for r in hold])
    out = []
    for k in (3, 6, 10, 14, 18):
        keep = {f for v in order.values() for f in v[:k]}
        rows = [r for r in train if r["language"] != "en" or r["template_family"] in keep]
        texts = [model_text(r["text"]) for r in rows]
        y = np.array([INTENT_NAMES.index(r["gold"]["intent"]) for r in rows])
        tf = fit_tfidf(texts, y, 32.0)
        coef, icpt = fit_embed(emb.embed(texts).astype(float), y, 30.0)
        p = (softmax(tf.logits(ht), 0.69) + softmax(He @ coef.T + icpt, 0.85)) / 2
        err = (p.argmax(1) != y_h).astype(float)
        out.append({"phrasings_per_intent": k, "n_train": len(rows), "holdout_intent_accuracy": round(1 - err.mean(), 4),
                    "holdout_aurc": round(aurc(p.max(1), err), 4)})
        print(out[-1])
    (ROOT / "outputs" / "learning_curve.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
