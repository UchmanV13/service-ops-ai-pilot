"""Pilot 2 holdout data: holdout_v2, shift_v2, paraphrase_v2.

Uses only the batch-3 phrasings in templates_v2.py (never trained or calibrated
on), plus the shared greeting/closing/noise pools. Identifiers are protected
from typo noise.

    python -m sopilot.generate_v2 --out data/tickets
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .generate import PRODUCTS, SHIFT_PRODUCTS, make_id, pii_line, typo, OVERRIDE_ELIGIBLE
from .taxonomy import INTENTS, SEVERITY, gold_action
from .templates_en import ASKS, CLOSINGS, DETAILS, FIELD_SENTENCES, GREETINGS, NAMES, SHIFT_CORES
from .templates_ml import ML_CLOSINGS, ML_FIELD, ML_GREETINGS, NOISE
from .templates_v2 import CORES_V2, INJECTIONS_V2, ML_CORES_V2, OVERRIDES_V2, SECONDARY_V2

SEED = 20261023
SIZES = {"holdout_v2": 1500, "shift_v2": 800}
ML_INTENTS = tuple(ML_CORES_V2["pl"])


def build(rng, split, n):
    shift = split == "shift_v2"
    names = list(INTENTS)
    base = rng.choices(names, weights=[INTENTS[k].weight for k in names])[0]
    lang = rng.choice(("pl", "de", "es")) if (base in ML_INTENTS and rng.random() < (0.5 if shift else 0.25)) else "en"
    it = INTENTS[base]
    fam = rng.choice(it.products)
    pool = PRODUCTS[fam] + (SHIFT_PRODUCTS.get(fam, []) * 3 if shift else [])
    product = rng.choice(pool)
    ptxt = ("Halden " + product) if product and rng.random() < 0.5 else product
    if lang == "en":
        if shift and rng.random() < 0.5:
            ci = rng.randrange(3)
            core, family = SHIFT_CORES[base][ci], f"{base}:en:shift{ci}"
        else:
            ci = rng.randrange(len(CORES_V2[base]))
            core, family = CORES_V2[base][ci], f"{base}:en:v2-{ci}"
        detail = rng.choice(DETAILS[base]) if rng.random() < 0.45 else ""
    else:
        core, family, detail = ML_CORES_V2[lang][base], f"{base}:{lang}:v2", ""
    core = core.replace("{product}", ptxt or "account")

    intent = base
    flags = {"override": None, "injection": False, "multi_issue": False, "secondary_intent": None, "pii": []}
    extra = []
    if lang == "en" and not it.critical:
        r = rng.random()
        eligible = [k for k, f in OVERRIDE_ELIGIBLE.items() if f(it, fam)]
        if eligible and r < 0.06:
            ov = rng.choice(eligible)
            extra.append(OVERRIDES_V2[ov])
            intent, flags["override"] = ov, ov
        elif r < 0.09:
            extra.append(rng.choice(INJECTIONS_V2))
            flags["injection"] = True
        elif r < 0.15:
            sec = rng.choice([k for k in SECONDARY_V2 if k != base])
            extra.append(SECONDARY_V2[sec])
            flags["multi_issue"], flags["secondary_intent"] = True, sec
            if SEVERITY[INTENTS[sec].priority] > SEVERITY[it.priority]:
                intent = sec

    present = {}
    for f in INTENTS[base].required:
        if rng.random() < 0.75:
            present[f] = make_id(f, rng, shift)
    if rng.random() < 0.12:
        f = rng.choice(("service_tag", "order_number", "case_number"))
        present.setdefault(f, make_id(f, rng, shift))

    name = rng.choice(NAMES)
    if lang == "en":
        greet, close, ask = rng.choice(GREETINGS), rng.choice(CLOSINGS), rng.choice(ASKS)
        field_s = [rng.choice(FIELD_SENTENCES[f]).format(v=v) for f, v in present.items()]
        noise = rng.choice(NOISE)
    else:
        greet, close, ask = rng.choice(ML_GREETINGS[lang]), rng.choice(ML_CLOSINGS[lang]), ""
        field_s = [ML_FIELD[lang][f].format(v=v) for f, v in present.items()]
        noise = ""
    body = " ".join(s for s in [core, detail, *extra, *field_s, noise, ask] if s)
    pii, kinds = pii_line(rng, name) if rng.random() < 0.35 else ("", [])
    flags["pii"] = kinds
    text = ((greet + "\n") if greet else "") + body + "\n" + (f"{close}\n{name}" if close else name) + (("\n" + pii) if pii else "")
    if shift:
        text = typo(text, rng, 0.06, protect_ids=True)
        if rng.random() < 0.3:
            text = text.lower()
    elif rng.random() < 0.15:
        text = typo(text, rng, 0.03, protect_ids=True)

    action, missing = gold_action(intent, set(present), multi_issue=flags["multi_issue"], injection=flags["injection"])
    gi = INTENTS[intent]
    return {"id": f"{split}-{n:05d}", "split": split, "text": text, "language": lang, "product": product,
            "product_family": fam, "channel": "chat" if shift else rng.choice(("email", "web_form", "chat")),
            "fields": present,
            "gold": {"intent": intent, "queue": gi.queue, "action": action, "priority": gi.priority, "critical": gi.critical,
                     "missing_fields": missing, "kb": list(gi.kb)},
            "base_intent": base, "flags": flags, "template_family": family}


def paraphrase(rng, n_groups=150):
    out = []
    names = [k for k in INTENTS if k != "privacy_request"]
    for g in range(n_groups):
        intent = rng.choice(names)
        it = INTENTS[intent]
        fam = rng.choice(it.products)
        product = rng.choice(PRODUCTS[fam])
        present = {f: make_id(f, rng) for f in it.required if rng.random() < 0.8}
        field_s = " ".join(FIELD_SENTENCES[f][0].format(v=v) for f, v in present.items())
        action, missing = gold_action(intent, set(present))
        for ci, core in enumerate(CORES_V2[intent]):
            out.append({"id": f"para2-{g:03d}-{ci}", "group": g, "split": "paraphrase_v2",
                        "text": f"Hi,\n{core.replace('{product}', product)} {field_s}\nThanks", "language": "en",
                        "product": product, "product_family": fam, "channel": "email", "fields": present,
                        "gold": {"intent": intent, "queue": it.queue, "action": action, "priority": it.priority,
                                 "critical": it.critical, "missing_fields": missing, "kb": list(it.kb)},
                        "base_intent": intent, "flags": {"override": None, "injection": False, "multi_issue": False,
                                                         "secondary_intent": None, "pii": []},
                        "template_family": f"{intent}:en:v2-{ci}"})
    return out


def main(out_dir="data/tickets"):
    out = Path(out_dir)
    res = {}
    for split, size in SIZES.items():
        rng = random.Random(f"{SEED}-{split}")
        rows = [build(rng, split, n) for n in range(size)]
        with open(out / f"{split}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        res[split] = len(rows)
    rows = paraphrase(random.Random(f"{SEED}-para"))
    with open(out / "paraphrase_v2.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    res["paraphrase_v2"] = len(rows)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/tickets")
    print(main(ap.parse_args().out))
