"""Qloo sets the money terms. Qloo's heatmap for an idea gives cells (a point and an affinity, 0 to 1); each cell is
placed in a US Metropolitan Statistical Area by its 2023 Census boundary (TIGER/Line tl_2023_us_cbsa, LSAD M1,
data/cbsa_msa_2023.json, simplified to 0.01 degree), and the metro with the highest mean affinity is the launch city.
The pre-order target is round(100 x that mean), at least 10, and the brief refunds every pre-order when that city does
not reach it by the first milestone's deadline. City, affinity and target sit in the brief's `launch`, inside the
criteria hash (knos.ready)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "cbsa_msa_2023.json"
MIN_TARGET = 10
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


def terms(cells: list[dict]) -> dict | None:
    """The launch city (top metro by mean heatmap affinity), its affinity and the pre-order target, or None when no
    heatmap cell falls in a US metro."""
    by: dict[str, list] = {}
    names: dict[str, str] = {}
    at: dict[str, list] = {}
    for c in cells or []:
        a = c.get("affinity")
        m = metro(c.get("lat"), c.get("lon"))
        if m and isinstance(a, (int, float)):
            by.setdefault(m["cbsa"], []).append(float(a))
            at.setdefault(m["cbsa"], []).append((c["lat"], c["lon"]))
            names[m["cbsa"]] = m["name"]
    if not by:
        return None
    ranked = sorted(by, key=lambda k: (-sum(by[k]) / len(by[k]), k))
    top = ranked[0]
    aff = round(sum(by[top]) / len(by[top]), 4)
    target = max(MIN_TARGET, round(100 * aff))
    return {"city": names[top], "cbsa": top, "affinity": aff, "target": target, "cells": len(by[top]),
            "metros": [{"city": names[k], "cbsa": k, "affinity": round(sum(by[k]) / len(by[k]), 4),
                        "lat": round(sum(x for x, _ in at[k]) / len(at[k]), 4), "lon": round(sum(y for _, y in at[k]) / len(at[k]), 4)}
                       for k in ranked[:5]],
            "refund_rule": REFUND.format(target=target, city=names[top]), "source": "Qloo heatmap; Census TIGER/Line 2023 metro boundaries"}


def brief(idea: str, t: dict) -> dict:
    """The Ready brief whose money terms Qloo set: one pre-order milestone in the launch city."""
    return {"title": f"Pre-orders for {idea}"[:160],
            "milestones": [{"key": "preorders", "name": f"Pre-orders from {t['city']}",
                            "target": f"{t['target']} pre-order customers from {t['city']}",
                            "verifier": {"kind": "machine", "check": "test_preorders_from_city"}, "deadline_days": DEADLINE_DAYS}],
            "kill_fee_bps": 0, "challenge_s": 86_400,
            "launch": {"city": t["city"], "cbsa": t["cbsa"], "affinity": t["affinity"], "target": t["target"], "refund_rule": t["refund_rule"]}}
