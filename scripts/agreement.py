"""Inter-annotator agreement for the blind labeling sheet.

Fill data/labeling/blind_sheet.csv twice (one copy per person), save as
labeler_a.csv and labeler_b.csv in data/labeling/, then run:

    python scripts/agreement.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "data" / "labeling"


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def load(name):
    with open(LAB / name, encoding="utf-8") as fh:
        return {r["id"]: r for r in csv.DictReader(fh)}


def main():
    if not (LAB / "labeler_a.csv").exists() or not (LAB / "labeler_b.csv").exists():
        print("Missing labeler_a.csv / labeler_b.csv in data/labeling/. Nothing to compute yet.")
        return 1
    a, b = load("labeler_a.csv"), load("labeler_b.csv")
    gold = {}
    for line in open(ROOT / "data" / "tickets" / "test.jsonl", encoding="utf-8"):
        r = json.loads(line)
        gold[r["id"]] = r["gold"]
    ids = [i for i in a if i in b and a[i]["intent"] and b[i]["intent"]]
    out = {"n": len(ids)}
    for key in ("intent", "action"):
        xa = [a[i][key] for i in ids]
        xb = [b[i][key] for i in ids]
        g = [gold[i][key] for i in ids]
        out[key] = {
            "kappa_a_vs_b": round(kappa(xa, xb), 3),
            "agree_a_vs_b": round(sum(x == y for x, y in zip(xa, xb)) / len(ids), 3),
            "agree_a_vs_gold": round(sum(x == y for x, y in zip(xa, g)) / len(ids), 3),
            "agree_b_vs_gold": round(sum(x == y for x, y in zip(xb, g)) / len(ids), 3),
        }
    print(json.dumps(out, indent=1))
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "agreement.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
