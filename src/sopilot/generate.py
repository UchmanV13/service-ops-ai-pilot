"""Synthetic ticket generator for Halden Devices (fictional).

Labels come from the labeling rules in taxonomy.gold_action, never from a model.
Phrasings are split by template family so test wording is unseen in training.

    python -m sopilot.generate --out data/tickets
"""
from __future__ import annotations

import argparse
import json
import random
import re
import string
from pathlib import Path

from .taxonomy import INTENTS, SEVERITY, gold_action
from .templates_en import (ASKS, CLOSINGS, CORES, DETAILS, FIELD_SENTENCES, GREETINGS, NAMES,
                           SHIFT_CORES)
from .templates_ml import (INJECTIONS, ML_CLOSINGS, ML_CORES, ML_FIELD, ML_GREETINGS, NOISE,
                           OVERRIDES, SECONDARY)

SEED = 20261022
SPLIT_SIZES = {"dev": 2400, "val": 1200, "test": 1500, "shift": 800}
SPLIT_INDEX = {"dev": 0, "val": 1, "test": 2}

PRODUCTS = {
    "laptop": ["Aero 13", "Aero 15", "Forge 16"],
    "desktop": ["Tower T5", "Mini M2"],
    "monitor": ["Clarity 27", "Clarity 32"],
    "dock": ["Dock D3"],
    "server": ["Stratus S2", "Stratus S4"],
    "none": [""],
}
SHIFT_PRODUCTS = {"laptop": ["Aero 14 (2027)"], "server": ["Vault V1 storage array"]}

ML_INTENTS = tuple(ML_CORES["pl"])
OVERRIDE_ELIGIBLE = {
    "battery_safety": lambda it, fam: fam == "laptop" and it.queue in ("software_support", "hardware_repair"),
    "data_loss": lambda it, fam: fam in ("laptop", "desktop") and it.name in ("os_recovery", "no_power", "slow_performance", "display_flicker", "fan_overheating"),
    "legal_threat": lambda it, fam: it.queue in ("billing_returns", "warranty_entitlement", "parts_logistics", "field_scheduling", "hardware_repair"),
    "enterprise_outage": lambda it, fam: fam in ("laptop", "desktop") and it.queue == "software_support",
}
SECONDARY_SEVERITY = {k: INTENTS[k].priority for k in SECONDARY}


def core_assignment(rng: random.Random) -> dict:
    """Assign each English core phrasing (24 per intent) to dev (14), val (4) or test (6)."""
    out = {}
    for intent, cores in CORES.items():
        idx = list(range(len(cores)))
        rng.shuffle(idx)
        out[intent] = {"dev": idx[:14], "val": idx[14:18], "test": idx[18:24]}
    return out


def make_id(kind: str, rng: random.Random, shift: bool = False) -> str:
    alnum = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    if kind == "service_tag":
        v = "HDN" + "".join(rng.choice(alnum) for _ in range(6))
        return v.lower() if shift and rng.random() < 0.3 else v
    if kind == "order_number":
        d = "".join(rng.choice(string.digits) for _ in range(8))
        return (f"ORD {d}" if shift and rng.random() < 0.3 else f"ORD-{d}")
    d = "".join(rng.choice(string.digits) for _ in range(7))
    return f"CS-{d}" if not (shift and rng.random() < 0.3) else f"case #{d}"


_ID_LIKE = re.compile(r"\d|^(?:hdn|ord|cs-)", re.IGNORECASE)


def typo(text: str, rng: random.Random, rate: float, protect_ids: bool = False) -> str:
    """Random swaps, drops and duplications. protect_ids=True (Pilot 2 data) never
    touches tokens that contain digits or look like identifiers."""
    words = text.split(" ")
    out = []
    for w in words:
        if protect_ids and _ID_LIKE.search(w):
            out.append(w)
            continue
        if len(w) > 3 and rng.random() < rate:
            i = rng.randrange(len(w) - 1)
            op = rng.choice(("swap", "drop", "dup"))
            if op == "swap":
                w = w[:i] + w[i + 1] + w[i] + w[i + 2:]
            elif op == "drop":
                w = w[:i] + w[i + 1:]
            else:
                w = w[:i] + w[i] + w[i:]
        out.append(w)
    return " ".join(out)


def pii_line(rng: random.Random, name: str) -> tuple[str, list]:
    kinds = []
    parts = []
    if rng.random() < 0.6:
        parts.append(f"{name.split()[0].lower()}.{name.split()[1].lower()}{rng.randint(1, 99)}@example.com")
        kinds.append("email")
    if rng.random() < 0.5:
        parts.append(f"+1 ({rng.randint(200, 989)}) {rng.randint(200, 989)}-{rng.randint(1000, 9999)}")
        kinds.append("phone")
    if rng.random() < 0.04:
        parts.append("card 4111 1111 1111 1111")
        kinds.append("card")
    return (" | ".join(parts), kinds) if parts else ("", [])


def render(rng, split, intent_name, *, lang, assign, shift):
    it = INTENTS[intent_name]
    fam = rng.choice(it.products)
    pool = PRODUCTS[fam] + (SHIFT_PRODUCTS.get(fam, []) * 3 if shift else [])
    product = rng.choice(pool)
    product_text = (("Halden " + product) if product and rng.random() < 0.5 else product)

    if lang == "en":
        if shift:
            if rng.random() < 0.5:
                ci = rng.randrange(3)
                core = SHIFT_CORES[intent_name][ci]
                family = f"{intent_name}:en:shift{ci}"
            else:
                ci = rng.randrange(len(CORES[intent_name]))
                core = CORES[intent_name][ci]
                family = f"{intent_name}:en:{ci}"
        else:
            ci = rng.choice(assign[intent_name][split])
            core = CORES[intent_name][ci]
            family = f"{intent_name}:en:{ci}"
        detail_pool = DETAILS[intent_name]
        detail = detail_pool[SPLIT_INDEX.get(split, rng.randrange(3))] if rng.random() < 0.45 else ""
    else:
        ci = SPLIT_INDEX[split] if not shift else rng.randrange(3)
        core = ML_CORES[lang][intent_name][ci]
        family = f"{intent_name}:{lang}:{ci}"
        detail = ""
    core = core.replace("{product}", product_text or "account")
    return it, fam, product, core, detail, family


def build_ticket(rng, split, n, assign, intent_weights):
    shift = split == "shift"
    names = list(INTENTS)
    base = rng.choices(names, weights=[intent_weights[k] for k in names])[0]
    ml_p = 0.5 if shift else 0.25
    lang = rng.choice(("pl", "de", "es")) if (base in ML_INTENTS and rng.random() < ml_p) else "en"

    it, fam, product, core, detail, family = render(rng, split, base, lang=lang, assign=assign, shift=shift)
    vidx = SPLIT_INDEX.get(split, rng.randrange(3))

    intent = base
    flags = {"override": None, "injection": False, "multi_issue": False, "secondary_intent": None, "pii": []}
    extra = []
    if lang == "en" and not it.critical:
        r = rng.random()
        eligible = [k for k, f in OVERRIDE_ELIGIBLE.items() if f(it, fam)]
        if eligible and r < 0.06:
            ov = rng.choice(eligible)
            extra.append(OVERRIDES[ov][vidx])
            intent = ov
            flags["override"] = ov
        elif r < 0.09:
            pool = INJECTIONS[2 * vidx: 2 * vidx + 2] if not shift else INJECTIONS
            extra.append(rng.choice(pool))
            flags["injection"] = True
        elif r < 0.15:
            sec = rng.choice([k for k in SECONDARY if k != base])
            extra.append(SECONDARY[sec])
            flags["multi_issue"] = True
            flags["secondary_intent"] = sec
            if SEVERITY[INTENTS[sec].priority] > SEVERITY[it.priority]:
                intent = sec

    # identifiers: required ones present with p=0.75; occasional irrelevant extra
    present = {}
    req = INTENTS[base].required
    for f in req:
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

    body = [s for s in [core, detail, *extra, *field_s, noise, ask] if s]
    text_parts = [greet] if greet else []
    text_parts.append(" ".join(body))
    signoff = f"{close}\n{name}" if close else name
    pii, kinds = pii_line(rng, name) if rng.random() < 0.35 else ("", [])
    flags["pii"] = kinds
    text = "\n".join(text_parts) + "\n" + signoff + (("\n" + pii) if pii else "")

    if shift:
        text = typo(text, rng, 0.06)
        if rng.random() < 0.3:
            text = text.lower()
    elif rng.random() < 0.15:
        text = typo(text, rng, 0.03)

    action, missing = gold_action(intent, set(present),
                                  multi_issue=flags["multi_issue"], injection=flags["injection"])
    gi = INTENTS[intent]
    return {
        "id": f"{split}-{n:05d}",
        "split": split,
        "text": text,
        "language": lang,
        "product": product,
        "product_family": fam,
        "channel": rng.choice(("email", "web_form", "chat")) if not shift else "chat",
        "fields": present,
        "gold": {
            "intent": intent,
            "queue": gi.queue,
            "action": action,
            "priority": gi.priority,
            "critical": gi.critical,
            "missing_fields": missing,
            "kb": list(gi.kb),
        },
        "base_intent": base,
        "flags": flags,
        "template_family": family,
    }


def paraphrase_groups(rng, assign, n_groups=150):
    """Same case (intent, product, identifiers) rendered with each of the 3 test phrasings."""
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
        for ci in assign[intent]["test"]:
            core = CORES[intent][ci].replace("{product}", product)
            out.append({
                "id": f"para-{g:03d}-{ci}", "group": g, "split": "paraphrase",
                "text": f"Hi,\n{core} {field_s}\nThanks", "language": "en", "product": product,
                "product_family": fam, "channel": "email", "fields": present,
                "gold": {"intent": intent, "queue": it.queue, "action": action, "priority": it.priority,
                         "critical": it.critical, "missing_fields": missing, "kb": list(it.kb)},
                "base_intent": intent, "flags": {"override": None, "injection": False, "multi_issue": False,
                                                 "secondary_intent": None, "pii": []},
                "template_family": f"{intent}:en:{ci}",
            })
    return out


def main(out_dir: str = "data/tickets") -> dict:
    rng = random.Random(SEED)
    assign = core_assignment(rng)
    weights = {k: v.weight for k, v in INTENTS.items()}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for split, size in SPLIT_SIZES.items():
        # val was re-sampled once (v2) after the first protocol run; see the charter change log
        srng = random.Random(f"{SEED}-{split}" + ("-v2" if split == "val" else ""))
        rows = [build_ticket(srng, split, n, assign, weights) for n in range(size)]
        with open(out / f"{split}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary[split] = len(rows)
    para = paraphrase_groups(random.Random(f"{SEED}-para"), assign)
    with open(out / "paraphrase.jsonl", "w", encoding="utf-8") as fh:
        for r in para:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary["paraphrase"] = len(para)
    (out / "core_assignment.json").write_text(json.dumps(assign, indent=1))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/tickets")
    print(main(ap.parse_args().out))
