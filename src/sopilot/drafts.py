"""Reply drafts. Deterministic templates grounded in the KB article or sandbox
lookup; every draft cites what it used. (An LLM drafter can replace this; see llm.py.)
"""
from __future__ import annotations

from .taxonomy import INTENTS

FIELD_LABEL = {"service_tag": "service tag (starts with HDN, on the label under the device)",
               "order_number": "order number (ORD- followed by 8 digits)",
               "case_number": "case number (CS- followed by 7 digits)"}


def draft(action: str, intent: str, article: dict | None, lookup: dict | None, missing: list) -> dict:
    it = INTENTS[intent]
    cites = [article["id"]] if article else []
    if action == "REQUEST_INFO":
        need = " and ".join(FIELD_LABEL[f] for f in missing)
        body = f"Thanks for contacting Halden Support. To look into this we need your {need}. Reply with it and we'll take it from there."
    elif action == "AUTO_REPLY_KB" and article:
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(article["steps"], 1))
        body = (f"Thanks for contacting Halden Support. {article['summary']}\n\n{steps}\n\n"
                f"If this doesn't solve it, reply to this message and a technician will pick it up. (Ref: {article['id']})")
    elif action == "AUTO_LOOKUP" and lookup:
        if intent == "warranty_status":
            state = "active" if lookup["active"] else "expired"
            body = f"Your device {lookup['service_tag']} has {lookup['plan']} coverage, {state}, ending {lookup['end_date']}."
        elif intent == "part_order_status":
            when = "delivered on" if lookup["status"] == "Delivered" else "expected"
            body = (f"Order {lookup['order_number']}: {lookup['status'].lower()} with {lookup['carrier']}, "
                    f"tracking {lookup['tracking']}, {when} {lookup['eta']}.")
        elif intent == "refund_status":
            done = f"was issued on {lookup['refund_issued']}" if lookup["refund_issued"] else f"is expected by {lookup['expected']}"
            body = f"We received your return on {lookup['return_received']}; the refund {done}. Banks can take 3 to 10 more days."
        else:
            body = f"Invoice {lookup['invoice']} for order {lookup['order_number']} has been re-sent to {lookup['sent_to']}."
        body = "Thanks for contacting Halden Support. " + body + " [SANDBOX DATA]"
    elif action == "AUTO_SCHEDULE_LINK" and lookup:
        body = (f"Thanks for contacting Halden Support. You can pick or change your technician window for case "
                f"{lookup['case_number']} here: {lookup['link']} [SANDBOX LINK]")
    elif action == "ESCALATE":
        body = (f"[Internal] Priority hand-off to {it.queue.replace('_', ' ')}. Customer-facing reply must come from the specialist team. "
                + (f"Guidance: {article['steps'][0]}" if article and article.get("steps") else ""))
    else:
        body = (f"[Draft for agent review] Suggested queue: {it.queue.replace('_', ' ')}. "
                + (f"Relevant procedure: {article['title']} ({article['id']}). {article['summary']}" if article else ""))
    return {"text": body, "citations": cites}
