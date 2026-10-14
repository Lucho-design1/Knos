"""No personal data goes to Qloo (Qloo hackathon kit, docs/SAFE_USE.md: "Do not send names, email addresses, device
identifiers, account IDs, location histories, or other personal data to Qloo"). Every argument of every MCP call is
checked here BEFORE it leaves the server; a refused call never reaches Qloo.

What a buyer gives Knos is things they like (public cultural signals: a brand, a film, a cuisine), never who they
are. This guard refuses what looks like identity data: an e-mail address, a phone number, a social handle, a URL,
an IP address, a card or account number, a street address, or a sentence about the person ("my name is").
"""
from __future__ import annotations

import re

MAX_ITEMS = 10
MAX_LEN = 80
SAFE = re.compile(r"^(\d{4}-\d{2}-\d{2}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
                  r"|urn:[a-z0-9:_.-]+|mock-[a-z0-9_-]+)$")
PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "an e-mail address"),
    (re.compile(r"(?<![\w-])@[A-Za-z0-9_]{2,}"), "a social handle"),
    (re.compile(r"https?://|www\.", re.I), "a link"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "an IP address"),
    (re.compile(r"(?:\+|\b)\d(?:[\s().-]?\d){6,}\b"), "a phone, card or account number"),
    (re.compile(r"\b(my|our)\s+(name|email|e-mail|phone|number|address|account|id|birthday|age)\b", re.I), "a detail about a person"),
    (re.compile(r"\bi\s*(am|'m)\s+(a|an)?\s*\d{1,3}\b", re.I), "a person's age"),
    (re.compile(r"\b\d{1,5}\s+\w+(\s\w+)?\s+(street|st|road|rd|avenue|ave|lane|ln|drive|dr|close|crescent)\b", re.I), "a street address"),
    (re.compile(r"\b(device|advertising|account|user|customer)[\s_-]?id\b", re.I), "an identifier"),
]


class PersonalData(ValueError):
    """Refused before any Qloo call: the text looks like personal data."""


def problems(value, where: str = "input") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out += problems(v, f"{where}.{k}")
    elif isinstance(value, (list, tuple)):
        if len(value) > MAX_ITEMS:
            out.append(f"{where}: at most {MAX_ITEMS} items")
        for i, v in enumerate(value):
            out += problems(v, f"{where}[{i}]")
    elif isinstance(value, str):
        if SAFE.match(value):      # a Qloo id or tag URN, or an ISO date: not free text
            return out
        if len(value) > MAX_LEN and not where.endswith(("idea",)):
            out.append(f"{where}: at most {MAX_LEN} characters")
        for rx, what in PATTERNS:
            if rx.search(value):
                out.append(f"{where} looks like {what}")
    return out


def check(value, where: str = "input") -> None:
    p = problems(value, where)
    if p:
        raise PersonalData("Knos sends no personal data to Qloo: " + "; ".join(p[:3])
                           + ". Name things you like (a brand, a film, a cuisine), not who you are.")
