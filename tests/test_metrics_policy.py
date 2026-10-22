import numpy as np

from sopilot.evaluation import choose_auto_threshold_ltt
from sopilot.metrics import aurc, cp_lower, cp_upper
from sopilot.pipeline import Params, decide
from sopilot.taxonomy import INTENT_NAMES


def test_clopper_pearson_rule_of_three():
    assert abs(cp_upper(0, 100) - 0.0295) < 0.001  # one-sided 95% upper bound with zero errors
    assert cp_lower(100, 100) > 0.97


def test_aurc_perfect_ranking_is_lower():
    err = np.array([0, 0, 0, 1, 1])
    assert aurc(np.array([0.9, 0.8, 0.7, 0.2, 0.1]), err) < aurc(np.array([0.1, 0.2, 0.3, 0.9, 0.8]), err)


def ev(intent="part_order_status", conf=0.97, fields=None, **kw):
    p = np.zeros(len(INTENT_NAMES))
    p[INTENT_NAMES.index(intent)] = conf
    p[INTENT_NAMES.index("driver_update")] += 1 - conf
    base = {"intent": intent, "confidence": conf, "probs": p, "p_critical": 0.0, "p_critical_binary": None,
            "critical_intent": "battery_safety", "guard_hits": [], "injection": [], "sentence_preds": [],
            "fields": fields if fields is not None else {"order_number": "ORD-12345678"}, "language": "en",
            "retrieval": [{"id": "KB-PL-01", "title": "", "score": 1.0}], "redacted_text": "", "pii_found": [], "top3": []}
    base.update(kw)
    return base


def test_policy_paths():
    P = Params(auto_threshold=0.9, critical_threshold=0.3)
    assert decide(ev(), P)["action"] == "AUTO_LOOKUP"
    assert decide(ev(fields={}), P)["action"] == "REQUEST_INFO"
    assert decide(ev(conf=0.8), P)["action"] == "HUMAN_REVIEW"
    assert decide(ev(guard_hits=[("battery_safety", "smoke")]), P)["action"] == "ESCALATE"
    assert decide(ev(p_critical=0.5), P)["action"] == "ESCALATE"
    assert decide(ev(injection=["ignore your previous instructions"]), P)["action"] == "HUMAN_REVIEW"
    off = decide(ev(), Params(auto_threshold=1.01))
    assert off["action"] == "HUMAN_REVIEW" and "off" in off["reasons"][0]


def test_sibling_guard_blocks_lookalike():
    e = ev(intent="warranty_status", fields={"service_tag": "HDN4K7Q2X"})
    e["probs"][INTENT_NAMES.index("ownership_transfer")] = 0.2
    assert decide(e, Params(auto_threshold=0.9, sibling_guard=0.1))["action"] == "HUMAN_REVIEW"
    assert decide(e, Params(auto_threshold=0.9))["action"] == "AUTO_LOOKUP"


def test_ltt_stops_at_first_failure():
    rows, evs = [], []
    for i in range(400):
        conf = 0.99 if i < 200 else 0.92
        wrong = i >= 200 and i % 4 == 0  # 25% errors in the lower band
        rows.append({"gold": {"intent": "part_order_status" if not wrong else "wrong_part", "action": "AUTO_LOOKUP" if not wrong else "HUMAN_REVIEW",
                              "critical": False, "queue": "parts_logistics"}, "template_family": str(i), "language": "en"})
        evs.append(ev(conf=conf))
    lam, trace = choose_auto_threshold_ltt(rows, evs, Params(critical_threshold=0.9), alpha=0.04, delta=0.05,
                                           grid=np.array([0.98, 0.95, 0.9]))
    # 0.98 and 0.95 automate only the clean band (0 errors in 200); 0.9 adds a 25%-error band and fails
    assert lam == 0.95
    assert trace[-1]["lambda"] == 0.9 and trace[-1]["p_value"] > 0.05
