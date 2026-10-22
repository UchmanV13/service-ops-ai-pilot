"""Single source of truth for intents, queues, actions and the labeling rules.

Everything here is for the fictional vendor Halden Devices. The labeling guide
(docs/03_labeling_guide.md) is generated from this file so the two cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field

AUTOMATED_ACTIONS = ("AUTO_REPLY_KB", "AUTO_LOOKUP", "AUTO_SCHEDULE_LINK", "REQUEST_INFO")
HUMAN_ACTIONS = ("HUMAN_REVIEW", "ESCALATE")
ALL_ACTIONS = AUTOMATED_ACTIONS + HUMAN_ACTIONS

QUEUES = (
    "software_support",
    "hardware_repair",
    "warranty_entitlement",
    "parts_logistics",
    "field_scheduling",
    "billing_returns",
    "enterprise_escalation",
    "trust_safety",
)

FIELD_NAMES = ("service_tag", "order_number", "case_number")


@dataclass(frozen=True)
class Intent:
    name: str
    queue: str
    action: str            # gold action when the request is complete and has no modifiers
    priority: str          # P1 (most urgent) .. P4
    critical: bool
    products: tuple        # product families the request can be about
    required: tuple = ()   # fields an automated action needs
    kb: tuple = ()         # relevant knowledge-base article ids
    weight: float = 1.0    # relative frequency in the synthetic stream
    description: str = ""


INTENTS: dict[str, Intent] = {i.name: i for i in [
    # software_support: knowledge-base answerable
    Intent("driver_update", "software_support", "AUTO_REPLY_KB", "P4", False, ("laptop", "desktop"), (), ("KB-SW-01",), 5, "How to find or install a driver"),
    Intent("bios_update", "software_support", "AUTO_REPLY_KB", "P4", False, ("laptop", "desktop"), (), ("KB-SW-02",), 3, "How to update BIOS/firmware safely"),
    Intent("os_recovery", "software_support", "AUTO_REPLY_KB", "P3", False, ("laptop", "desktop"), (), ("KB-SW-03",), 4, "Reinstall or recover the operating system"),
    Intent("wifi_drops", "software_support", "AUTO_REPLY_KB", "P3", False, ("laptop", "desktop"), (), ("KB-SW-04",), 4, "Wi-Fi or Bluetooth disconnects"),
    Intent("display_flicker", "software_support", "AUTO_REPLY_KB", "P3", False, ("laptop", "desktop"), (), ("KB-SW-05",), 3, "Screen flicker or resolution problems after an update"),
    Intent("slow_performance", "software_support", "AUTO_REPLY_KB", "P4", False, ("laptop", "desktop"), (), ("KB-SW-06",), 3, "Device is slow"),
    # hardware_repair
    Intent("no_power", "hardware_repair", "HUMAN_REVIEW", "P2", False, ("laptop", "desktop", "monitor"), ("service_tag",), ("KB-HW-01",), 4, "Device will not power on"),
    Intent("screen_damage", "hardware_repair", "HUMAN_REVIEW", "P3", False, ("laptop", "monitor"), ("service_tag",), ("KB-HW-02",), 3, "Cracked or physically damaged screen"),
    Intent("keyboard_failure", "hardware_repair", "HUMAN_REVIEW", "P3", False, ("laptop",), ("service_tag",), ("KB-HW-03",), 2, "Keys or trackpad not working"),
    Intent("fan_overheating", "hardware_repair", "HUMAN_REVIEW", "P3", False, ("laptop", "desktop", "server"), ("service_tag",), ("KB-HW-04",), 3, "Fan noise, overheating, thermal shutdowns"),
    Intent("dead_pixels", "hardware_repair", "AUTO_REPLY_KB", "P4", False, ("monitor", "laptop"), (), ("KB-HW-05",), 2, "Dead or stuck pixels (policy + self-test)"),
    Intent("dock_not_detected", "hardware_repair", "AUTO_REPLY_KB", "P3", False, ("dock",), (), ("KB-HW-06",), 3, "Dock or external display not detected"),
    # warranty_entitlement
    Intent("warranty_status", "warranty_entitlement", "AUTO_LOOKUP", "P4", False, ("laptop", "desktop", "monitor", "server", "dock"), ("service_tag",), ("KB-WA-01",), 5, "What warranty does my device have"),
    Intent("warranty_extension", "warranty_entitlement", "HUMAN_REVIEW", "P4", False, ("laptop", "desktop", "monitor", "server"), ("service_tag",), ("KB-WA-02",), 2, "Buy or extend coverage"),
    Intent("ownership_transfer", "warranty_entitlement", "HUMAN_REVIEW", "P4", False, ("laptop", "desktop", "monitor"), ("service_tag",), ("KB-WA-03",), 1.5, "Transfer warranty to a new owner"),
    Intent("accidental_damage", "warranty_entitlement", "HUMAN_REVIEW", "P3", False, ("laptop", "monitor"), ("service_tag",), ("KB-WA-04",), 2, "Is a drop or spill covered"),
    # parts_logistics
    Intent("part_order_status", "parts_logistics", "AUTO_LOOKUP", "P3", False, ("laptop", "desktop", "monitor", "server", "dock"), ("order_number",), ("KB-PL-01",), 5, "Where is my replacement part"),
    Intent("wrong_part", "parts_logistics", "HUMAN_REVIEW", "P2", False, ("laptop", "desktop", "monitor", "server"), ("order_number",), ("KB-PL-02",), 2, "Wrong or missing part delivered"),
    Intent("return_label", "parts_logistics", "HUMAN_REVIEW", "P4", False, ("laptop", "desktop", "monitor", "server", "dock"), ("order_number",), ("KB-PL-03",), 1.5, "Need a label to return the defective part"),
    # field_scheduling
    Intent("schedule_onsite", "field_scheduling", "AUTO_SCHEDULE_LINK", "P3", False, ("laptop", "desktop", "server"), ("case_number",), ("KB-FS-01",), 3, "Book a technician visit for an approved case"),
    Intent("reschedule_visit", "field_scheduling", "AUTO_SCHEDULE_LINK", "P3", False, ("laptop", "desktop", "server"), ("case_number",), ("KB-FS-01",), 2.5, "Move an existing technician visit"),
    Intent("technician_no_show", "field_scheduling", "HUMAN_REVIEW", "P2", False, ("laptop", "desktop", "server"), ("case_number",), ("KB-FS-02",), 1.5, "Technician did not arrive"),
    # billing_returns
    Intent("refund_status", "billing_returns", "AUTO_LOOKUP", "P3", False, ("laptop", "desktop", "monitor", "dock"), ("order_number",), ("KB-BR-01",), 4, "Where is my refund"),
    Intent("invoice_copy", "billing_returns", "AUTO_LOOKUP", "P4", False, ("laptop", "desktop", "monitor", "server", "dock"), ("order_number",), ("KB-BR-02",), 3, "Send me an invoice copy"),
    Intent("duplicate_charge", "billing_returns", "HUMAN_REVIEW", "P2", False, ("laptop", "desktop", "monitor", "dock"), ("order_number",), ("KB-BR-03",), 2, "Charged twice or wrong amount"),
    Intent("return_request", "billing_returns", "HUMAN_REVIEW", "P3", False, ("laptop", "desktop", "monitor", "dock"), ("order_number",), ("KB-BR-04",), 2.5, "Return a product for a refund"),
    # enterprise_escalation (critical)
    Intent("enterprise_outage", "enterprise_escalation", "ESCALATE", "P1", True, ("server",), (), ("KB-EN-01",), 1.2, "Business-wide outage: server down or many devices failing"),
    Intent("raid_degraded", "enterprise_escalation", "ESCALATE", "P1", True, ("server",), (), ("KB-EN-02",), 0.8, "Storage array or RAID degraded / disk failed"),
    Intent("data_loss", "enterprise_escalation", "ESCALATE", "P1", True, ("laptop", "desktop", "server"), (), ("KB-EN-03",), 0.8, "Customer data lost or unreadable"),
    # trust_safety (critical)
    Intent("battery_safety", "trust_safety", "ESCALATE", "P1", True, ("laptop",), (), ("KB-TS-01",), 0.8, "Swelling battery, smoke, burning smell, sparks, heat damage"),
    Intent("security_incident", "trust_safety", "ESCALATE", "P1", True, ("laptop", "desktop"), (), ("KB-TS-02",), 0.6, "Stolen device, compromised account or firmware tampering"),
    Intent("legal_threat", "trust_safety", "ESCALATE", "P2", True, ("laptop", "desktop", "monitor"), (), ("KB-TS-03",), 0.6, "Threat of legal or regulatory action"),
    Intent("privacy_request", "trust_safety", "ESCALATE", "P2", True, ("none",), (), ("KB-TS-04",), 0.6, "Request to access or delete personal data"),
]}

INTENT_NAMES = tuple(INTENTS)
CRITICAL_INTENTS = tuple(n for n, i in INTENTS.items() if i.critical)
AUTOMATABLE_INTENTS = tuple(n for n, i in INTENTS.items() if i.action in AUTOMATED_ACTIONS)


def queue_of(intent: str) -> str:
    return INTENTS[intent].queue


@dataclass
class GoldLabel:
    intent: str
    queue: str
    action: str
    priority: str
    critical: bool
    missing_fields: list = field(default_factory=list)


def gold_action(intent: str, present_fields: set, *, multi_issue: bool = False,
                injection: bool = False) -> tuple[str, list]:
    """Labeling rules from the guide, applied in order.

    1. Critical intents always escalate.
    2. A message containing an instruction aimed at the system (prompt injection) goes to a person.
    3. A message with two separate requests goes to a person.
    4. Automated intents with a missing required identifier get REQUEST_INFO.
    5. Otherwise the intent's base action.
    """
    it = INTENTS[intent]
    missing = [f for f in it.required if f not in present_fields]
    if it.critical:
        return "ESCALATE", missing
    if injection or multi_issue:
        return "HUMAN_REVIEW", missing
    if it.action in AUTOMATED_ACTIONS and missing:
        return "REQUEST_INFO", missing
    return it.action, missing


SEVERITY = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
