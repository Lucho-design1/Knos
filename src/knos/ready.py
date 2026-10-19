"""Ready to fund: whether a brief is clear enough to lock money on (docs: the IDT check). Deterministic, no AI scoring.

The one check the web app, /mcp, the HTTP API and the knos_pay client (knos.ideas.commit) all call. A brief is a list
of milestones; each milestone needs
  target    measurable: a number with its unit ("p95 under 300 ms", "12 samples") or a named test ("test_login",
            "tests/test_api.py::test_refund", check "build / lint")
  verifier  machine: the GitHub check or test name that decides it; or
            human (lab results, documents): what is measured, how, who measures it, where the record is published
            (the DOE SMART fields)
  deadline  seconds from funding (deadline_s, 60 s to 90 days) or whole days (deadline_days)
and no vague word (VAGUE) in its name, target or verifier. The answer is Ready, or Not ready with every missing field
by name and a one-tap rewrite template per milestone. The criteria hash is the sha256 of the canonical JSON of the
fields that decide payment (plus the kill fee and the challenge window); it is fixed at lock.
"""
from __future__ import annotations

import hashlib
import json
import re

VAGUE = ("better", "faster", "slower", "clean", "cleaner", "robust", "improve", "improved", "improves", "improvement",
         "progress", "modern", "modernize", "nice", "good", "great", "optimize", "optimise", "optimized", "scalable",
         "seamless", "efficient", "enhance", "enhanced", "polish", "polished", "appropriate", "adequate", "significant",
         "user-friendly", "intuitive", "high quality", "best", "etc", "asap", "soon", "some", "various", "reasonable")
UNITS = ("%", "ms", "s", "sec", "secs", "second", "seconds", "min", "mins", "minute", "minutes", "h", "hr", "hrs", "hour",
         "hours", "day", "days", "week", "weeks", "kb", "mb", "gb", "tb", "b", "bytes", "kib", "mib", "gib", "rps", "qps",
         "req/s", "fps", "x", "usd", "eur", "$", "units", "unit", "samples", "sample", "tests", "test", "runs", "run", "users",
         "user", "items", "rows", "files", "pages", "page", "errors", "error", "defects", "defect", "issues", "issue",
         "points", "point", "score", "c", "°c", "k", "mm", "cm", "m", "km", "g", "kg", "mg", "µg", "ug", "ml", "l", "µl",
         "ul", "nm", "µm", "um", "mol", "mmol", "µmol", "mm/s", "v", "mv", "a", "ma", "w", "mw", "kw", "hz", "khz", "mhz",
         "ghz", "db", "ppm", "ppb", "cells", "cell", "reads", "devices", "device", "units/day", "documents", "document",
         "sections", "section", "signatures", "signature", "customers", "customer", "weeks", "months", "month", "lines",
         "commits", "prs", "accuracy", "auc", "f1", "rmse", "mae", "iops", "ops", "cycles", "boards", "parts", "batches")
MIN_DEADLINE_S, MAX_DEADLINE_S = 60, 90 * 86_400
DEFAULT_CHALLENGE_S = 72 * 3600
MAX_KILL_FEE_BPS = 5000
_NUM_UNIT = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
                       + r")(?![\w])", re.I)
_TEST = re.compile(r"(?:\btest_[A-Za-z0-9_]+|\b[\w./-]+\.(?:py|js|ts|mjs|rs|go)::[\w\[\]-]+|\b[\w./-]*tests?/[\w./-]+|"
                   r"check\s+[\"'`][^\"'`]{2,100}[\"'`])")
_CHECK_NAME = re.compile(r"^[\w .:/()\[\]@,+#-]{2,100}$")
HUMAN_FIELDS = ("what", "how", "who", "where")


def _text(v, n: int = 300) -> str:
    return re.sub(r"\s+", " ", v).strip()[:n] if isinstance(v, str) else ""


def vague_words(text: str) -> list[str]:
    low = f" {text.lower()} "
    return sorted({w for w in VAGUE if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)})


def measurable(target: str) -> bool:
    return bool(_NUM_UNIT.search(target) or _TEST.search(target))


def deadline_s(m: dict) -> int | None:
    d = m.get("deadline_s")
    if d is None and m.get("deadline_days") is not None:
        d = m.get("deadline_days")
        d = d * 86_400 if isinstance(d, int) and not isinstance(d, bool) else None
    if isinstance(d, bool) or not isinstance(d, int) or not MIN_DEADLINE_S <= d <= MAX_DEADLINE_S:
        return None
    return d


def normal(m: dict, i: int = 0) -> dict:
    """One milestone's deciding fields, normalised (the form the hash and the order memo are made from)."""
    raw = m.get("verifier")
    v: dict = raw if isinstance(raw, dict) else {}
    kind = v.get("kind") if v.get("kind") in ("machine", "human") else ("machine" if v.get("check") else "human" if any(v.get(x) for x in HUMAN_FIELDS) else "")
    ver = {"kind": kind, "check": _text(v.get("check"), 100)} if kind == "machine" else \
        {"kind": kind, **{f: _text(v.get(f), 200) for f in HUMAN_FIELDS}} if kind == "human" else {"kind": ""}
    key = _text(m.get("key"), 40) or f"m{i + 1}"
    return {"key": re.sub(r"[^a-z0-9_]", "_", key.lower())[:40], "name": _text(m.get("name"), 160), "target": _text(m.get("target"), 300),
            "verifier": ver, "deadline_s": deadline_s(m)}


def check_milestone(m: dict, i: int = 0) -> dict:
    n = normal(m, i)
    missing, vague = [], []
    if len(n["name"]) < 3:
        missing.append("name")
    if not n["target"]:
        missing.append("target")
    elif not measurable(n["target"]):
        missing.append("target: a number with its unit, or a named test")
    v = n["verifier"]
    if not v["kind"]:
        missing.append("verifier")
    elif v["kind"] == "machine":
        if not v["check"]:
            missing.append("verifier.check: the GitHub check or test name")
        elif not _CHECK_NAME.match(v["check"]):
            missing.append("verifier.check: letters, digits, spaces and . : / ( ) [ ] - only")
    else:
        missing += [f"verifier.{f}" for f in HUMAN_FIELDS if len(v[f]) < 3]
    if n["deadline_s"] is None:
        missing.append("deadline: 60 seconds to 90 days")
    words = " ".join([n["name"], n["target"], *(x for k, x in v.items() if k != "kind")])
    vague = vague_words(words)
    ok = not missing and not vague
    return {"key": n["key"], "ready": ok, "missing": missing, "vague": vague, "milestone": n,
            "rewrite": None if ok else rewrite(n, vague)}


def rewrite(n: dict, vague: list[str]) -> dict:
    """The one-tap rewrite: the milestone with every missing or vague field turned into a slot to fill."""
    v = n["verifier"]
    name = n["name"]
    for w in vague:
        name = re.sub(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", "<number and unit>", name, flags=re.I)
    target = n["target"] if n["target"] and measurable(n["target"]) and not vague_words(n["target"]) else \
        "<number> <unit> on <named test or measurement>"
    if v.get("kind") == "human":
        ver = {"kind": "human", **{f: v[f] if len(v[f]) >= 3 and not vague_words(v[f]) else f"<{f}>" for f in HUMAN_FIELDS}}
    else:
        ver = {"kind": "machine", "check": v.get("check") if v.get("check") and not vague_words(v.get("check", "")) else
               "<GitHub check or test name>"}
    return {"key": n["key"], "name": name or "<what is delivered>", "target": target, "verifier": ver,
            "deadline_days": (n["deadline_s"] // 86_400 or 1) if n["deadline_s"] else 14}


def terms(brief: dict) -> dict:
    kf = brief.get("kill_fee_bps", 0)
    ch = brief.get("challenge_s", DEFAULT_CHALLENGE_S)
    return {"kill_fee_bps": kf if isinstance(kf, int) and not isinstance(kf, bool) else None,
            "challenge_s": ch if isinstance(ch, int) and not isinstance(ch, bool) else None}


def criteria_hash(brief: dict) -> str:
    ms = [normal(m, i) for i, m in enumerate(brief.get("milestones") or [])]
    body = {"v": 1, "milestones": ms, **terms(brief)}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def check(brief: dict) -> dict:
    """Ready, or Not ready with the exact missing fields and a rewrite template per milestone. Free, sends nothing."""
    if not isinstance(brief, dict):
        brief = {}
    ms = brief.get("milestones")
    rows = [check_milestone(m if isinstance(m, dict) else {}, i) for i, m in enumerate(ms if isinstance(ms, list) else [])]
    problems = [] if rows else ["milestones: at least one"]
    if len(rows) > 12:
        problems.append("milestones: at most 12")
    if len({r["key"] for r in rows}) != len(rows):
        problems.append("milestones: each key once")
    t = terms(brief)
    if t["kill_fee_bps"] is None or not 0 <= t["kill_fee_bps"] <= MAX_KILL_FEE_BPS:
        problems.append("kill_fee_bps: 0 to 5000 (what the maker keeps if the buyer cancels)")
    if t["challenge_s"] is None or not 60 <= t["challenge_s"] <= 30 * 86_400:
        problems.append("challenge_s: 60 seconds to 30 days (the dispute window after a referee verdict)")
    missing = problems + [f"{r['key']}.{f}" for r in rows for f in r["missing"]] + \
        [f"{r['key']}: vague word '{w}', say a number and unit instead" for r in rows for w in r["vague"]]
    ok = not missing
    return {"ready": ok, "label": "Ready" if ok else "Not ready", "missing": missing, "milestones": rows,
            "criteria_hash": criteria_hash(brief) if ok else None, **t,
            "rule": "each milestone: a measurable target, a verifier (a GitHub check, or what/how/who/where) and a deadline; no vague words"}


class NotReady(ValueError):
    def __init__(self, result: dict):
        self.result = result
        super().__init__("Not ready: " + "; ".join(result["missing"][:8]))


def require(brief: dict) -> dict:
    r = check(brief)
    if not r["ready"]:
        raise NotReady(r)
    return r
