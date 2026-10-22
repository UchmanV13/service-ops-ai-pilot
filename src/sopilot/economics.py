"""Net value per 1,000 tickets versus an all-human baseline.

All inputs come from config/economics.json and are illustrative assumptions.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_config():
    return json.loads((ROOT / "config" / "economics.json").read_text())


def net_value(outs, a: dict) -> dict:
    """outs: list of outcome dicts from evaluation.outcome. Returns per-1,000 figures in USD."""
    rate = a["analyst_cost_per_hour"] / 60
    srate = a["specialist_cost_per_hour"] / 60
    mm = a["manual_minutes"]
    saved_min = cost_usd = 0.0
    parts = {"automation_savings": 0.0, "assisted_triage_savings": 0.0, "spot_checks": 0.0, "wrong_automation": 0.0,
             "inappropriate_automation": 0.0, "misroutes": 0.0, "false_escalations": 0.0, "missed_critical": 0.0}
    for o in outs:
        if o["auto"]:
            if o["correct_auto"]:
                m = mm["triage_and_route"] + mm[o["gold_action"]]
                saved_min += m
                parts["automation_savings"] += m * rate
                c = a["spot_check_share_of_automated"] * a["spot_check_minutes"] * rate
                parts["spot_checks"] -= c
                cost_usd += c
            elif o["inappropriate"] and not o["critical"]:  # automated critical tickets are charged below as missed
                c = a["inappropriate_automation_cost"]["rework_minutes"] * rate + a["inappropriate_automation_cost"]["goodwill_usd"]
                parts["inappropriate_automation"] -= c
                cost_usd += c
            elif not o["critical"]:
                c = a["wrong_automation_cost"]["rework_minutes"] * rate + a["wrong_automation_cost"]["goodwill_usd"]
                parts["wrong_automation"] -= c
                cost_usd += c
        elif o["escalated"]:
            if o["critical"]:
                m = a["assisted_triage_minutes_saved_when_queue_correct"]
                saved_min += m
                parts["assisted_triage_savings"] += m * rate
            else:
                c = a["false_escalation_specialist_minutes"] * srate
                parts["false_escalations"] -= c
                cost_usd += c
        else:
            if o["queue_ok"]:
                m = a["assisted_triage_minutes_saved_when_queue_correct"]
                saved_min += m
                parts["assisted_triage_savings"] += m * rate
            else:
                c = a["misroute_rework_minutes"] * rate
                parts["misroutes"] -= c
                cost_usd += c
        if o["critical"] and not o["escalated"]:
            parts["missed_critical"] -= a["missed_critical_cost_usd"]
            cost_usd += a["missed_critical_cost_usd"]
    n = len(outs)
    scale = 1000 / n
    maint = (a["monthly_maintenance_hours"] * a["analyst_cost_per_hour"] + a["monthly_infra_usd"]) / a["monthly_tickets"] * 1000
    gross = saved_min * rate * scale
    net = gross - cost_usd * scale - maint
    return {"net_usd_per_1000": round(net, 2), "gross_savings_usd_per_1000": round(gross, 2),
            "costs_usd_per_1000": round(cost_usd * scale, 2), "maintenance_usd_per_1000": round(maint, 2),
            "analyst_hours_saved_per_1000": round(saved_min * scale / 60, 2),
            "components_usd_per_1000": {k: round(v * scale, 2) for k, v in parts.items()} | {"maintenance": -round(maint, 2)}}


def pessimistic(base: dict, mult: dict) -> dict:
    a = copy.deepcopy(base)
    a["manual_minutes"] = {k: v * mult["manual_minutes"] for k, v in a["manual_minutes"].items()}
    a["assisted_triage_minutes_saved_when_queue_correct"] *= mult["assisted_triage_minutes_saved_when_queue_correct"]
    for k in ("wrong_automation_cost", "inappropriate_automation_cost"):
        a[k] = {kk: vv * mult["error_costs"] for kk, vv in a[k].items()}
    a["misroute_rework_minutes"] *= mult["error_costs"]
    a["false_escalation_specialist_minutes"] *= mult["error_costs"]
    a["missed_critical_cost_usd"] *= mult["missed_critical_cost_usd"]
    a["monthly_maintenance_hours"] *= mult["maintenance"]
    a["monthly_infra_usd"] *= mult["maintenance"]
    return a


TORNADO_KEYS = [
    ("analyst_cost_per_hour", None), ("manual_minutes", "*"), ("assisted_triage_minutes_saved_when_queue_correct", None),
    ("misroute_rework_minutes", None), ("false_escalation_specialist_minutes", None), ("specialist_cost_per_hour", None),
    ("missed_critical_cost_usd", None), ("monthly_maintenance_hours", None), ("wrong_automation_cost", "*"),
    ("inappropriate_automation_cost", "*"),
]


def tornado(outs, base: dict, low=0.5, high=1.5):
    ref = net_value(outs, base)["net_usd_per_1000"]
    rows = []
    for key, sub in TORNADO_KEYS:
        vals = []
        for m in (low, high):
            a = copy.deepcopy(base)
            if sub == "*":
                a[key] = {k: v * m for k, v in a[key].items()}
            else:
                a[key] = a[key] * m
            vals.append(net_value(outs, a)["net_usd_per_1000"])
        rows.append({"assumption": key, "low": vals[0], "high": vals[1], "swing": round(abs(vals[1] - vals[0]), 2)})
    rows.sort(key=lambda r: -r["swing"])
    return {"reference": ref, "multipliers": [low, high], "rows": rows}


def break_even_missed_critical(outs, base: dict):
    """Largest cost per missed critical ticket at which net value stays >= 0."""
    a = copy.deepcopy(base)
    a["missed_critical_cost_usd"] = 0.0
    v0 = net_value(outs, a)
    missed = sum(1 for o in outs if o["critical"] and not o["escalated"])
    if missed == 0:
        return None
    per1000 = missed * 1000 / len(outs)
    return round(v0["net_usd_per_1000"] / per1000, 2)
