"""test_qloo_sets_terms, live: for each of the 20 T2 ideas (scripts/qloo_vs_open_signals.py IDEAS), the live demand
check (POST /api/check). An idea with heatmap cells must carry a Ready brief whose hashed launch block holds the launch
city (of the metros holding at least 3 cells, the highest mean affinity; else the most cells), its mean affinity, cell
count and 2023 population, and the target max(10, round(population / 100,000 x affinity)); the live Ready check
(POST /api/ready) answers Ready, and moving the affinity by 0.01 changes the criteria hash. An idea with no cells after
the retry by its top matched tag must say "Qloo has no map for this idea yet, so Knos sets no launch city." and carry no
launch block. Pass: every idea in its case does so, and the ideas with cells have at least 5 distinct targets.

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
OUT = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world") / "test_qloo_sets_terms.txt"
REFUND = "If fewer than {target} pre-orders come from {city} by the first milestone deadline, every pre-order is refunded."


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(APP + path, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "knos-test"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def ideas() -> list[str]:
    src = (ROOT / "scripts" / "qloo_vs_open_signals.py").read_text(encoding="utf-8")
    return re.findall(r'\("[A-Za-z0-9_ -]+",\s*"([^"]+)"\)', src[src.index("IDEAS"):])[:20]


NO_MAP = "Qloo has no map for this idea yet, so Knos sets no launch city."


def one(idea: str) -> tuple[str, bool, str, int | None]:
    """(case, ok, what was seen, target)."""
    rep = post("/api/check", {"idea": idea})
    t, b = rep.get("terms"), rep.get("brief")
    if not t:
        ok = rep.get("no_map") == NO_MAP and not b
        return "no map", ok, f"no-map line {'shown' if rep.get('no_map') == NO_MAP else 'missing'}, launch block {'absent' if not b else 'present'}", None
    lt = (b or {}).get("launch") or {}
    want = max(10, round(t["population"] / 100_000 * t["affinity"]))
    rows = t.get("metros") or []
    three = [r for r in rows if r["cells"] >= 3 and r.get("population")]
    pick = max(three, key=lambda r: (r["affinity"], r["cells"], r["cbsa"])) if three else         max((r for r in rows if r.get("population")), key=lambda r: (r["cells"], r["affinity"], r["cbsa"]))
    fields = all(lt.get(k) == t[k] for k in ("city", "affinity", "cells", "population", "target"))
    if not (fields and t["target"] == want and pick["cbsa"] == t["cbsa"]
            and lt.get("refund_rule") == REFUND.format(target=want, city=t["city"])):
        return "map", False, f"launch block does not follow the rule: {json.dumps(lt)[:160]}", t.get("target")
    r1 = post("/api/ready", {"brief": b})
    if not r1.get("ready") or (r1.get("launch") or {}).get("population") != t["population"]:
        return "map", False, f"not Ready: {r1.get('missing')}", t["target"]
    b2 = copy.deepcopy(b)
    b2["launch"]["affinity"] = round(t["affinity"] - 0.01 if t["affinity"] > 0.5 else t["affinity"] + 0.01, 4)
    r2 = post("/api/ready", {"brief": b2})
    if not r2.get("criteria_hash") or r2["criteria_hash"] == r1["criteria_hash"]:
        return "map", False, "moving the affinity by 0.01 left the criteria hash unchanged", t["target"]
    return "map", True, (f"{t['city']} ({t['cells']} of {t.get('heatmap_cells')} cells), affinity {t['affinity']}, population {t['population']:,}, "
                         f"target {t['target']}, hash {r1['criteria_hash'][:10]} -> {r2['criteria_hash'][:10]}"), t["target"]


def main() -> int:
    lines, cases, bad, targets = [], {"map": 0, "no map": 0}, 0, []
    rows = ideas()
    for idea in rows:
        try:
            case, ok, why, target = one(idea)
        except Exception as e:  # noqa: BLE001
            case, ok, why, target = "error", False, f"{type(e).__name__}: {str(e)[:100]}", None
        cases[case] = cases.get(case, 0) + 1
        bad += not ok
        if target is not None and ok:
            targets.append(target)
        lines.append(f"{'ok  ' if ok else 'FAIL'} {case:6} {idea[:44]:44} {why}")
    distinct = len(set(targets))
    passed = bad == 0 and len(rows) == 20 and distinct >= 5
    lines.append(f"{'PASS' if passed else 'FAIL'} test_qloo_sets_terms: {cases['map']} ideas with a map, each a hashed launch block, "
                 f"{distinct} distinct targets {sorted(set(targets))}; {cases['no map']} with no map, each saying so with no launch block; "
                 f"{bad} wrong" + (f"; {cases['error']} errors" if cases.get("error") else ""))
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
