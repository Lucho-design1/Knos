"""What each Qloo signal changes on a card, from the published table (scripts/qloo_ablation.py writes it to
docs/reference/qloo_ablation.json and a copy beside this module): for a recorded sample card, the call families whose
removal changes its launch city, its target or its verdict "decide" it, and every other call is "context". Derived
values only; nothing here asks Qloo."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TABLE = Path(__file__).with_name("data") / "qloo_ablation.json"
# a Qloo call family -> the report fields its answers fill (check.gather), and what they are when it is removed
FAMILIES = {
    "search (the matched products)": {"matches": [], "leader": None, "tags": []},
    "demographics": {"who": None},
    "audiences": {"audiences": [], "who_wants": [], "buyer_group": None},
    "compare (the leader)": {"versus": None},
    "trending": {"trend": {}},
    "recommendations": {"recommended": None},
    "heatmap": {"where": []},
    "destinations": {"cities": []},
    "places": {"places": []},
    "tags (persona)": {"persona": [], "persona_all": []},
    "brand ladder": {"ladder": []},
}


def moved(r: dict) -> bool:
    return r["city"][0] != r["city"][1] or r["target"][0] != r["target"][1] or r["label"][0] != r["label"][1]


@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    try:
        return json.loads(TABLE.read_text(encoding="utf-8"))["rows"]
    except (OSError, ValueError, KeyError):
        return []


def _srcs(value) -> set[int]:
    """The call numbers a report field cites (its "src", or its items')."""
    items = value if isinstance(value, list) else [value]
    return {int(x["src"]) for x in items if isinstance(x, dict) and isinstance(x.get("src"), int)}


def for_card(rep: dict) -> dict | None:
    """{"line", "decides": [call numbers], "families"} for a card the table holds; None for any other card."""
    rows = [r for r in _rows() if str(r.get("chip") or "").lower() == str(rep.get("idea") or "").lower() and r["removed"] != "every Qloo answer"]
    if not rows:
        return None
    deciding = [r["removed"] for r in rows if moved(r)]
    calls = set()
    for fam in deciding:
        for field in FAMILIES.get(fam, {}):
            calls |= _srcs(rep.get(field))
    names = [f.split(" (")[0] for f in deciding]
    line = (f"What each Qloo signal changes here: removing {', '.join(names[:-1]) + ' or ' + names[-1] if len(names) > 1 else names[0]} changes the "
            f"launch city, the target or the verdict; the other {len(rows) - len(deciding)} signals change none of them.") if names else \
        f"What each Qloo signal changes here: removing any one of its {len(rows)} signals changes neither the launch city, the target nor the verdict."
    return {"line": line, "decides": sorted(calls), "families": deciding}
