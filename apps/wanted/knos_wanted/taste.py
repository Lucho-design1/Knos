"""The films a film's fans also love, from Knos's own Qloo client (the REST client behind "they also love"): the film
resolved by Qloo search (type urn:entity:movie, the first result whose release year matches), then Qloo insights
(filter.type urn:entity:movie, signal.interests.entities set to it, take 20). GET /api/taste/movie answers the
derived names and years only, never a Qloo response body."""
from __future__ import annotations


def _year(e: dict) -> int | None:
    p = e.get("properties") or {}
    y = str(p.get("release_year") or str(p.get("release_date") or "")[:4])
    return int(y) if y.isdigit() else None


def also_love_movie(client, title: str, year: int | None, take: int = 20) -> dict:
    from .check import _results
    title = " ".join(str(title or "").split())[:120]
    if not title or year is None:
        raise ValueError("title and year are needed")
    found = [e for e in _results(client.get("/search", {"query": title, "types": "urn:entity:movie", "take": 10})["body"])
             if e.get("entity_id")]
    pick = next((e for e in found if _year(e) == year), None)
    out: dict = {"title": title, "year": year, "searched": [{"name": e.get("name"), "year": _year(e)} for e in found]}
    if pick is None:
        return {**out, "resolved": None, "films": []}
    body = client.get("/v2/insights", {"filter.type": "urn:entity:movie", "signal.interests.entities": pick["entity_id"], "take": take})["body"]
    ents = ((body or {}).get("results") or {}).get("entities") or []
    return {**out, "resolved": {"name": pick.get("name"), "year": _year(pick), "id": pick["entity_id"]},
            "films": [{"name": e.get("name"), "year": _year(e)} for e in ents[:take] if e.get("name")]}
