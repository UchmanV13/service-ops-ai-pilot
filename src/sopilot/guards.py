"""Deterministic guards that run before any model sees a ticket.

1. PII redaction (emails, phone numbers, payment card numbers). Identifiers the
   workflow needs (service tag, order and case numbers) are kept.
2. Prompt-injection detection: text aimed at the support system or an AI.
3. Hard escalation rules: phrases from the labeling guide's critical list.

The rules were written from the labeling guide. Their author also wrote the
synthetic templates, so recall on the synthetic splits is optimistic; the
hand-written and shift sets are the fairer test.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, list[str]]:
    found = []

    def card(m):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append("card")
            return "[CARD]"
        return m.group(0)

    text = CARD.sub(card, text)
    if EMAIL.search(text):
        found.append("email")
        text = EMAIL.sub("[EMAIL]", text)

    def phone(m):
        s = m.group(0)
        # never touch order/case numbers
        before = text[max(0, m.start() - 4):m.start()].upper()
        if "ORD" in before or "CS-" in before:
            return s
        found.append("phone")
        return "[PHONE]"

    text = PHONE.sub(phone, text)
    return text, sorted(set(found))


INJECTION_PATTERNS = [
    r"\bignore (?:all |any )?(?:your |the |my )?(?:previous |prior |above )?(?:instructions|rules|policy|policies)\b",
    r"\bignore all rules\b",
    r"\bdisregard (?:the |your |all )?(?:policy|policies|instructions|rules)\b",
    r"^\s*system\s*:", r"\bSYSTEM\s*:",
    r"\[\s*admin[^\]]*\]", r"\badmin override\b",
    r"\bnote to the (?:ai|bot|assistant|automated system)\b",
    r"\binstruction for the (?:ai|bot|assistant|automated system)\b",
    r"\b(?:assistant|ai|bot)\s*,\s*(?:disregard|ignore|approve|send|mark|issue)\b",
    r"\b(?:auto-?approve|mark (?:this|it) (?:ticket )?as resolved|close it without review|skip verification)\b",
    r"\breveal (?:the )?internal\b",
]
_INJ = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> list[str]:
    return [m.group(0) for p in _INJ for m in [p.search(text)] if m]


# Critical phrases from the labeling guide. Each rule maps to a critical intent.
HARD_RULES = {
    "battery_safety": [
        r"\bburning inside\b", r"\bsomething is burning\b", r"\bburn(?:ed|t)? my (?:leg|hand|lap)\b", r"\bdangerously hot\b", r"\bdiscolou?r",
        r"\bpushed up from (?:underneath|below)\b", r"\bbeing pushed up\b", r"\blifting because\b", r"\bexpand(?:ing|ed)\b", r"\binflated\b", r"\bhissing\b",
        r"\bsmok(?:e|ed|ing)\b", r"\bburn(?:ing|t)? (?:smell|plastic)\b", r"\bsmells? (?:like )?(?:burn|burnt|hot plastic|chemical)",
        r"\bspark(?:s|ed|ing)?\b", r"\bswell(?:ing|ed)?\b", r"\bswollen\b", r"\bbulg(?:e|es|ed|ing)\b", r"\bpuff(?:ed|y)\b",
        r"\bcaught fire\b", r"\bmelt(?:ed|ing)\b", r"\bbattery (?:is )?leaking\b", r"\bon fire\b",
        # pl / de / es
        r"\bpuchn", r"\bdym", r"\bspalenizn", r"\bspuchni", r"\bbläht", r"\brauch", r"\bbrandgeruch", r"\bhincha", r"\bhumo\b", r"\bquemado\b",
    ],
    "data_loss": [
        r"\bneeds formatting\b", r"\bunformatted\b", r"\bnone of my data\b", r"\bshow no files\b", r"\bpartitions disappeared\b",
        r"\b(?:isn't|not) recognized and my (?:work )?(?:files|data)\b", r"\bcorrupted and won't open\b", r"\bfiles are (?:now )?(?:corrupted|showing zero bytes)\b",
        r"\bzero bytes\b", r"\blost (?:months|years|everything)\b", r"\b(?:documents folder|desktop) (?:is )?(?:empty|vanished)\b", r"\bvanished after\b",
        r"\bno longer accessible\b", r"\bcan't recover\b", r"\bshows? as empty\b",
        r"\b(?:lost|lose) (?:all )?(?:my |our )?(?:files|data|documents|photos|work)\b", r"\b(?:files|data|documents|photos) (?:are |is |seem to be )?(?:gone|lost|vanished|disappeared)\b",
        r"\bdisappeared from\b", r"\bdata (?:is )?gone\b", r"\b(?:wiped|erased) and (?:my|our) data\b", r"\b(?:volume|drive|disk|files?|data) (?:is |are |now )?unreadable\b",
        r"\bnie jest wykrywany, a są na nim moje dane\b", r"\bstraciłem dane\b", r"\bpliki zniknęły\b", r"\bdaten sind weg\b",
        r"\bdateien sind\b.*\bverschwunden\b", r"\bperdí mis datos\b", r"\barchivos desaparecieron\b",
    ],
    "enterprise_outage": [
        r"\bbusiness stopped\b", r"\bevery user\b", r"\blost access\b", r"\bevery location\b", r"\bhospital\b", r"\ball .{0,30}\bnodes\b",
        r"\bevery machine\b", r"\bfactory line\b", r"\bpayroll\b", r"\be-?commerce\b", r"\bcall cent(?:er|re)\b", r"\bcrash loop\b", r"\bhypervisor\b",
        r"\ball vms\b", r"\bwhole team\b", r"\ball \d+ (?:laptops|devices|machines|computers)\b", r"\b\d+ (?:people|agents|users|employees) (?:can't|cannot) work\b",
        r"\b(?:nobody|no one) can work\b", r"\boperations (?:are )?stopped\b", r"\bdown for every\b",
        r"\bproduction (?:server|outage|system)\b", r"\bsev(?:erity)?\s*-?1\b", r"\bentire (?:office|site|department|company)\b",
        r"\b(?:whole|entire) (?:site|office|department) (?:is )?down\b", r"\bcluster (?:went )?down\b", r"\boutage\b",
        r"\b(?:all|hundreds of|every) (?:of our )?(?:\d+ )?(?:devices|machines|laptops|computers|nodes)\b",
    ],
    "raid_degraded": [
        r"\bstorage pool\b", r"\blost a (?:drive|disk)\b", r"\bmissing drive\b", r"\bhot spare\b", r"\brebuild(?:ing)?\b", r"\blost redundancy\b",
        r"\bmirrored disks?\b", r"\bvirtual disk\b", r"\bstorage array\b",r"\braid\b", r"\bdegraded\b", r"\bfailed (?:physical )?(?:disk|drive)\b", r"\bpredictive failure\b", r"\barray\b.*\boffline\b"],
    "security_incident": [
        r"\bbreak-in\b", r"\bcompromised\b", r"\bwasn't me\b", r"\bfrom another country\b", r"\blost at the airport\b", r"\bleft in a taxi\b",
        r"\bfailed verification\b", r"\bthink it was modified\b", r"\bnobody on our team made\b", r"\bfake update\b", r"\blocked until i pay\b",
        r"\btook control\b", r"\bmalware\b", r"\bdidn't install\b",
        r"\bstolen\b", r"\bransom\b", r"\bencrypted and\b", r"\bhacked\b", r"\brootkit\b", r"\btamper(?:ed|ing)\b",
        r"\bwithout my permission\b", r"\bunauthori[sz]ed\b", r"\bpretending to be (?:your )?support\b",
    ],
    "legal_threat": [
        r"\blegal team\b", r"\blegally\b", r"\bregulator\b", r"\bcontract breach\b", r"\bintent to sue\b", r"\bsmall claims\b", r"\bformal complaint\b",
        r"\blawyer\b", r"\battorney\b", r"\bsolicitor", r"\bsu(?:e|ing)\b", r"\bcourt\b", r"\blegal (?:action|complaint|department)\b",
        r"\bconsumer protection\b", r"\bconsumer agency\b", r"\btrading standards\b", r"\bbetter business bureau\b",
    ],
    "privacy_request": [
        r"\bdata protection\b", r"\bcontact details removed\b", r"\bcustomer profile\b", r"\bright to be forgotten\b", r"\brecords of my support\b",
        r"\bcall recordings\b", r"\bobject to you processing\b",
        r"\bgdpr\b", r"\bccpa\b", r"\bpersonal (?:data|information|details)\b", r"\bdata subject\b", r"\barticle 15\b",
        r"\b(?:delete|erase|remove) (?:all )?(?:my|the) (?:data|information|account|contact details|phone number|recordings)\b",
    ],
}
_HARD = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in HARD_RULES.items()}


def hard_escalation(text: str) -> list[tuple[str, str]]:
    """Return (critical_intent, matched_phrase) pairs, most severe first."""
    hits = []
    for intent, pats in _HARD.items():
        for p in pats:
            m = p.search(text)
            if m:
                hits.append((intent, m.group(0)))
                break
    return hits
