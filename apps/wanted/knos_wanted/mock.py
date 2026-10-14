"""MOCK (synthetic, not real Qloo data): bodies shaped like the examples and schemas in Qloo's public docs.

Used whenever QLOO_API_KEY is not set. Every value here is generated from a hash of the request, so the same idea
gives the same mock report; none of it describes real people, places or brands. Names carry "(synthetic)", ids start
with "mock-". The shapes follow docs/QLOO_SOURCES.md; where Qloo's docs do not spell out a field's layout (the
per-result explainability object, the items of /v2/analysis/compare) the mock uses the simplest layout the docs'
words allow, and knos_wanted.report reads both that layout and plausible alternatives.
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import date, timedelta

from .geo import encode

# A few city centres for the mock heatmap's geometry only (public coordinates, rounded).
CENTRES = {"london": (51.507, -0.128), "new york": (40.713, -74.006), "nyc": (40.713, -74.006), "lagos": (6.524, 3.379),
           "los angeles": (34.052, -118.244), "paris": (48.857, 2.352), "berlin": (52.520, 13.405), "tokyo": (35.676, 139.650),
           "san francisco": (37.775, -122.419), "chicago": (41.878, -87.630), "toronto": (43.653, -79.383)}
AGES = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]


def _rng(endpoint: str, params: dict) -> random.Random:
    key = endpoint + "|" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "x"


def _id(text: str) -> str:
    return "mock-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _split(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x]


def _entity(name: str, subtype: str, r: random.Random) -> dict:
    return {"name": f"{name} (synthetic)", "entity_id": _id(name.lower()), "type": "urn:entity", "subtype": subtype,
            "properties": {"description": "MOCK entity: synthetic, not real Qloo data"},
            "popularity": round(r.uniform(0.35, 0.99), 4), "tags": []}


def respond(endpoint: str, params: dict) -> dict:
    r = _rng(endpoint, params)
    duration = r.randint(20, 120)
    if endpoint == "search":
        q = params.get("query", "")
        subtype = _split(params.get("types"))[:1] or ["urn:entity:brand"]
        n = min(int(params.get("take", 3)), 5)
        names = [q.strip().title()] + [f"{q.strip().title()} {s}" for s in ("Co", "Collective", "Studio", "Lab")]
        return {"success": True, "duration": duration / 1000, "results": [_entity(nm, subtype[0], r) for nm in names[:n]]}
    if endpoint == "tags":
        q = params.get("filter.query", "")
        n = min(int(params.get("take", 3)), 5)
        words = [q] + [f"{q} {s}" for s in ("lifestyle", "culture", "fans", "enthusiasts")]
        return {"success": True, "duration": duration, "results": {"tags": [
            {"tag_id": f"urn:tag:keyword:mock:{_slug(w)}", "name": f"{w.title()} (synthetic)", "types": ["urn:entity:brand"],
             "subtype": "urn:tag:keyword:mock", "tag_value": f"urn:tag:keyword:mock:{_slug(w)}", "query": {}} for w in words[:n]]}}
    if endpoint == "demographics":
        out = []
        for eid in _split(params.get("signal.interests.entities")) + _split(params.get("signal.interests.tags")):
            raw = [r.uniform(-0.5, 0.5) for _ in AGES]
            g = round(r.uniform(-0.3, 0.3), 2)
            out.append({"entity_id": eid, "query": {"age": {a: round(v, 2) for a, v in zip(AGES, raw)},
                                                    "gender": {"male": g, "female": -g}}})
        return {"success": True, "results": {"demographics": out}, "duration": duration}
    if endpoint == "heatmap":
        place = (params.get("filter.location.query") or "london").lower()
        lat, lon = CENTRES.get(place, CENTRES["london"])
        cells = []
        for _ in range(int(params.get("take", 12))):
            la, lo = lat + r.uniform(-0.12, 0.12), lon + r.uniform(-0.18, 0.18)
            cells.append({"location": {"latitude": round(la, 6), "longitude": round(lo, 6), "geohash": encode(la, lo, 6)},
                          "query": {"affinity": round(r.uniform(0.2, 1.0), 4), "affinity_rank": round(r.uniform(0.2, 1.0), 4),
                                    "popularity": round(r.uniform(0.2, 1.0), 4)}})
        cells.sort(key=lambda c: -c["query"]["affinity"])
        return {"success": True, "results": {"heatmap": cells}}
    if endpoint == "insights":
        subtype = params.get("filter.type", "urn:entity:brand")
        inputs = _split(params.get("signal.interests.entities"))
        tags = _split(params.get("signal.interests.tags"))
        wanted = _split(params.get("filter.results.entities"))
        n = min(int(params.get("take", 8)), 50)
        if wanted:
            ents = [{"name": f"entity {w[-6:]} (synthetic)", "entity_id": w, "type": "urn:entity", "subtype": subtype,
                     "properties": {}, "popularity": round(r.uniform(0.3, 0.95), 4), "tags": []} for w in wanted]
        else:
            ents = [_entity(f"Neighbour {k + 1}", subtype, r) for k in range(n)]
        for e in ents:
            contrib = [{"entity_id": i, "score": round(r.uniform(0.1, 1.0), 3)} for i in inputs]
            contrib += [{"tag_id": t, "score": round(r.uniform(0.1, 1.0), 3)} for t in tags]
            e["query"] = {"affinity": round(r.uniform(0.2, 0.99), 4),
                          "measurements": {"audience_growth": round(r.uniform(-0.1, 0.15), 4)},
                          "explainability": {"signal.interests.entities": [c for c in contrib if "entity_id" in c],
                                             "signal.interests.tags": [c for c in contrib if "tag_id" in c]}}
        ents.sort(key=lambda e: -e["query"]["affinity"])
        agg = {f"top_{k}": [{"entity_id": i, "score": round(r.uniform(0.1, 1.0), 3)} for i in inputs + tags] for k in (3, 5, 10)}
        return {"success": True, "results": {"entities": ents, "duration": duration}, "query": {"explainability": agg}}
    if endpoint == "trending":
        try:
            start = date.fromisoformat(params.get("filter.start_date", ""))
            end = date.fromisoformat(params.get("filter.end_date", ""))
        except ValueError:
            end = date(2026, 10, 1)
            start = end - timedelta(days=84)
        slope = r.uniform(-0.15, 0.25)
        pct, rank, rows, d = r.uniform(40, 80), r.randint(400, 4000), [], start
        while d <= end and len(rows) < 60:
            prev_rank = rank
            pct = max(0.0, min(100.0, pct + slope * 7 + r.uniform(-1, 1)))
            rank = max(1, int(rank * (1 - slope / 10)))
            rows.append({"date": d.isoformat(), "population_percentile": round(pct, 2), "population_rank": rank,
                         "population_rank_velocity": prev_rank - rank, "velocity_fold_change": round(1 + slope / 5, 3),
                         "population_percent_delta": round(slope, 3)})
            d += timedelta(days=7)
        return {"success": True, "duration": duration, "results": {"trending": rows}}
    if endpoint == "compare":
        n = min(int(params.get("take", 6)), 20)
        return {"success": True, "duration": duration / 1000,
                "results": [_entity(f"Shared taste {k + 1}", "urn:entity:brand", r) for k in range(n)]}
    raise ValueError(endpoint)
