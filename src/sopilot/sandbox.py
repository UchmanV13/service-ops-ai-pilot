"""SANDBOX back-office for the demo. Every record here is fabricated on the fly
from a hash of the identifier. Nothing is read from or written to a real system.
"""
from __future__ import annotations

import datetime as dt
import hashlib

TODAY = dt.date(2026, 10, 22)


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


def warranty_lookup(service_tag: str) -> dict:
    h = _h(service_tag)
    plans = ["Basic (mail-in)", "Premium (onsite next business day)", "Premium + Accidental Damage"]
    end = TODAY + dt.timedelta(days=(h % 1400) - 300)
    return {"sandbox": True, "service_tag": service_tag, "plan": plans[h % 3],
            "end_date": end.isoformat(), "active": end >= TODAY}


def part_order_lookup(order_number: str) -> dict:
    h = _h(order_number)
    status = ["Processing", "Shipped", "Out for delivery", "Delivered"][h % 4]
    eta = TODAY - dt.timedelta(days=1 + h % 3) if status == "Delivered" else TODAY + dt.timedelta(days=1 + h % 5)
    return {"sandbox": True, "order_number": order_number, "status": status, "carrier": "Example Freight",
            "tracking": f"EXF{h % 10**10:010d}", "eta": eta.isoformat()}


def refund_lookup(order_number: str) -> dict:
    h = _h(order_number + "r")
    received = TODAY - dt.timedelta(days=h % 20)
    issued = received + dt.timedelta(days=5)
    return {"sandbox": True, "order_number": order_number, "return_received": received.isoformat(),
            "refund_issued": issued.isoformat() if issued <= TODAY else None,
            "expected": issued.isoformat()}


def invoice_lookup(order_number: str) -> dict:
    return {"sandbox": True, "order_number": order_number, "invoice": f"INV-{_h(order_number) % 10**8:08d}",
            "sent_to": "the email address on the order"}


def scheduling_link(case_number: str) -> dict:
    return {"sandbox": True, "case_number": case_number,
            "link": f"https://schedule.example.invalid/{case_number}?t={_h(case_number) % 10**6:06d}"}


LOOKUPS = {
    "warranty_status": ("service_tag", warranty_lookup),
    "part_order_status": ("order_number", part_order_lookup),
    "refund_status": ("order_number", refund_lookup),
    "invoice_copy": ("order_number", invoice_lookup),
}
