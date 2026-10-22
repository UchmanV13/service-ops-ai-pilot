import json
from pathlib import Path

from sopilot.taxonomy import INTENTS, gold_action

DATA = Path(__file__).resolve().parents[1] / "data" / "tickets"


def rows(split):
    return [json.loads(line) for line in open(DATA / f"{split}.jsonl", encoding="utf-8")]


def test_labeling_rules_order():
    assert gold_action("battery_safety", set(), injection=True)[0] == "ESCALATE"
    assert gold_action("part_order_status", {"order_number"}, injection=True)[0] == "HUMAN_REVIEW"
    assert gold_action("warranty_status", set())[0] == "REQUEST_INFO"
    assert gold_action("warranty_status", {"service_tag"})[0] == "AUTO_LOOKUP"
    assert gold_action("no_power", set())[0] == "HUMAN_REVIEW"


def test_every_label_follows_the_rules():
    for split in ("dev", "val", "test", "holdout_v2", "shift_v2", "handwritten"):
        for r in rows(split):
            g = r["gold"]
            assert g["queue"] == INTENTS[g["intent"]].queue
            assert g["critical"] == INTENTS[g["intent"]].critical


def test_phrasing_families_do_not_leak():
    fam = {s: {r["template_family"] for r in rows(s) if r["language"] == "en"} for s in ("dev", "val", "test", "holdout_v2")}
    assert not fam["dev"] & fam["test"] and not fam["val"] & fam["test"] and not fam["dev"] & fam["val"]
    for s in ("dev", "val", "test"):
        assert not fam[s] & fam["holdout_v2"]
