"""test_qloo_sets_terms, live: for each of the 20 T2 ideas (scripts/qloo_vs_open_signals.py IDEAS), the live demand
check (POST /api/check) returns a Ready brief whose launch city is the top Census metro of Qloo's heatmap, whose
pre-order target is round(100 x that metro's mean affinity), at least 10, and whose refund rule names both. The live
Ready check (POST /api/ready) answers Ready with those three values inside the criteria hash: the same brief with the
affinity moved by 0.01 hashes differently.

    python scripts/test_qloo_sets_terms.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

APP = "https://knos.onrender.com"
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world")) / "test_qloo_sets_terms.txt"
REFUND = "If fewer than {target} pre-orders come from {city} by the first milestone deadline, every pre-order is refunded."


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(APP + path, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "knos-test"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def ideas() -> list[str]:
    src = (ROOT / "scripts" / "qloo_vs_open_signals.py").read_text(encoding="utf-8")
    return re.findall(r'\("[A-Za-z0-9_ -]+",\s*"([^"]+)"\)', src[src.index("IDEAS"):])[:20]


def one(idea: str) -> tuple[bool, str]:
    rep = post("/api/check", {"idea": idea})
    t, b = rep.get("terms"), rep.get("brief")
    if not t or not b:
        return False, f"no heatmap metro ({len(rep.get('where') or [])} heatmap cells)"
    lt = b.get("launch") or {}
    want = max(10, round(100 * t["affinity"]))
    if not (lt.get("city") == t["city"] and lt.get("affinity") == t["affinity"] and lt.get("target") == t["target"] == want
            and lt.get("refund_rule") == REFUND.format(target=want, city=t["city"])):
        return False, f"terms do not follow the rule: {json.dumps(lt)[:160]}"
    r1 = post("/api/ready", {"brief": b})
    if not r1.get("ready") or (r1.get("launch") or {}).get("affinity") != t["affinity"]:
        return False, f"not Ready: {r1.get('missing')}"
    b2 = copy.deepcopy(b)
    b2["launch"]["affinity"] = round(t["affinity"] - 0.01 if t["affinity"] > 0.5 else t["affinity"] + 0.01, 4)
    r2 = post("/api/ready", {"brief": b2})
    if not r2.get("criteria_hash") or r2["criteria_hash"] == r1["criteria_hash"]:
        return False, "moving the affinity by 0.01 left the criteria hash unchanged"
    return True, f"{t['city']} (CBSA {t['cbsa']}), affinity {t['affinity']}, target {t['target']}, hash {r1['criteria_hash'][:10]} -> {r2['criteria_hash'][:10]}"


def main() -> int:
    lines, good = [], 0
    rows = ideas()
    for idea in rows:
        try:
            ok, why = one(idea)
        except Exception as e:  # noqa: BLE001
            ok, why = False, f"{type(e).__name__}: {str(e)[:100]}"
        good += ok
        lines.append(f"{'ok  ' if ok else 'FAIL'} {idea[:44]:44} {why}")
    lines.append(f"{'PASS' if good == len(rows) == 20 else 'FAIL'} test_qloo_sets_terms: {good} of {len(rows)} T2 ideas with a Ready brief whose launch city, "
                 "affinity and pre-order target come from Qloo's heatmap and sit inside the criteria hash")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if good == len(rows) == 20 else 1


if __name__ == "__main__":
    sys.exit(main())
