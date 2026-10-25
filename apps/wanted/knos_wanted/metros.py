"""Qloo sets the money terms. Qloo's heatmap for an idea gives cells (a point and an affinity, 0 to 1); each cell is
placed in a US Metropolitan Statistical Area by its 2023 Census boundary (TIGER/Line tl_2023_us_cbsa, LSAD M1,
data/cbsa_msa_2023.json, simplified to 0.01 degree, with each metro's Vintage 2023 population). Of the metros holding
at least 3 cells, the highest mean affinity is the launch city (when none holds 3, the one with the most cells). The
pre-order target is max(10, round(population / 100,000 x mean affinity)), and the brief refunds every pre-order when
that city does not reach it by the first milestone's deadline. The launch block (city, affinity, cell count, population,
target) sits inside the criteria hash (knos.ready)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "cbsa_msa_2023.json"
MIN_TARGET = 10
MIN_CELLS = 3
NO_MAP = "Qloo has no map for this idea yet, so Knos sets no launch city."
DEADLINE_DAYS = 30
REFUND = "If fewer than {target} pre-orders come from {city} by the first milestone deadline, every pre-order is refunded."


@lru_cache(maxsize=1)
def _metros() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))["metros"]


def _inside(lon: float, lat: float, ring: list) -> bool:
    hit, j = False, len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i], ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def metro(lat, lon) -> dict | None:
    """The Metropolitan Statistical Area that holds the point, or None."""
    if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
        return None
    for m in _metros():
        x0, y0, x1, y1 = m["bbox"]
        if x0 <= lon <= x1 and y0 <= lat <= y1 and any(_inside(lon, lat, r) for r in m["rings"]):
            return m
    return None


def flat(cells: list[dict]) -> bool:
    """Every cell at one affinity: Qloo's default for a signal it could not use, never a map of this idea's people."""
    return len(cells) > 1 and len({c.get("affinity") for c in cells}) == 1


def stats(cells: list[dict]) -> list[dict]:
    """Each US metro holding heatmap cells: its cell count, mean affinity, centre and 2023 population. Sorted by the
    ranking the where-demand test reads: metros with at least 3 cells by mean affinity, then those with 1 or 2."""
    by: dict[str, dict] = {}
    for c in cells or []:
        a = c.get("affinity")
        m = metro(c.get("lat"), c.get("lon"))
        if m and isinstance(a, (int, float)):
            row = by.setdefault(m["cbsa"], {"cbsa": m["cbsa"], "city": m["name"], "pop": m.get("pop"), "_a": [], "_at": []})
            row["_a"].append(float(a))
            row["_at"].append((c["lat"], c["lon"]))
    out = []
    for r in by.values():
        n = len(r["_a"])
        out.append({"cbsa": r["cbsa"], "city": r["city"], "cells": n, "affinity": round(sum(r["_a"]) / n, 4), "population": r["pop"],
                    "lat": round(sum(x for x, _ in r["_at"]) / n, 4), "lon": round(sum(y for _, y in r["_at"]) / n, 4)})
    return sorted(out, key=lambda r: (r["cells"] < MIN_CELLS, -r["affinity"], -r["cells"], r["cbsa"]))


def launch(rows: list[dict]) -> dict | None:
    """The launch city: of the metros holding at least 3 cells, the highest mean affinity; when none holds 3, the one
    with the most cells, ties by mean affinity. A metro with no population estimate (Puerto Rico) cannot set a target."""
    rows = [r for r in rows if r.get("population")]
    three = [r for r in rows if r["cells"] >= MIN_CELLS]
    if three:
        return max(three, key=lambda r: (r["affinity"], r["cells"], r["cbsa"]))
    return max(rows, key=lambda r: (r["cells"], r["affinity"], r["cbsa"])) if rows else None


def terms(cells: list[dict]) -> dict | None:
    """The launch city, its mean affinity, cell count and population, and the pre-order target
    max(10, round(population / 100,000 x mean affinity)); None when no cell falls in a US metro."""
    if flat(cells):
        return None
    rows = stats(cells)
    top = launch(rows)
    if not top:
        return None
    target = max(MIN_TARGET, round(top["population"] / 100_000 * top["affinity"]))
    return {"city": top["city"], "cbsa": top["cbsa"], "affinity": top["affinity"], "cells": top["cells"], "population": top["population"],
            "target": target, "heatmap_cells": len(cells), "metros": rows,
            "refund_rule": REFUND.format(target=target, city=top["city"]),
            "source": "Qloo heatmap; Census TIGER/Line 2023 metro boundaries; Census Vintage 2023 population estimates"}


def brief(idea: str, t: dict) -> dict:
    """The Ready brief whose money terms Qloo set: one pre-order milestone in the launch city."""
    return {"title": f"Pre-orders for {idea}"[:160],
            "milestones": [{"key": "preorders", "name": f"Pre-orders from {t['city']}",
                            "target": f"{t['target']} pre-order customers from {t['city']}",
                            "verifier": {"kind": "machine", "check": "test_preorders_from_city"}, "deadline_days": DEADLINE_DAYS}],
            "kill_fee_bps": 0, "challenge_s": 86_400,
            "launch": {"city": t["city"], "cbsa": t["cbsa"], "affinity": t["affinity"], "cells": t["cells"], "population": t["population"],
                       "target": t["target"], "refund_rule": t["refund_rule"]}}
