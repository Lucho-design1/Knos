"""Qloo's concentration index of each launch city, recomputed from a report's heatmap cells (stdin: the report JSON as
GET /api/report gives it): each metro's mean cell affinity (knos_wanted.metros.stats), rescaled over the metros, the
highest 100 and the lowest 0, as Qloo's page defines it. Prints {city: index} as JSON. Used by test_concentration.mjs.
    python scripts/concentration_check.py < report.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "wanted"))
from knos_wanted import metros  # noqa: E402


def main() -> int:
    rep = json.load(sys.stdin)
    rows = metros.stats(rep.get("where") or [])
    aff = [r["affinity"] for r in rows if isinstance(r.get("affinity"), (int, float))]
    lo, hi = (min(aff), max(aff)) if aff else (0, 0)
    out = {r["city"]: (round(100 * (r["affinity"] - lo) / (hi - lo)) if hi > lo else 100) for r in rows if isinstance(r.get("affinity"), (int, float))}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
