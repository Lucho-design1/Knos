"""The Wanted Report: who wants it, where, how strong against rivals, rising or not, and why.

Directional demand evidence, not a sales forecast. Each section names the Qloo call it came from; a section whose
call this key does not serve (or that failed) says so and the rest of the report still stands.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from . import planner
from .geo import decode
from .qloo import MOCK_LABEL, Qloo, QlooError

FRAMING = "Directional demand evidence, not a sales forecast."
LIVE_LABEL = "LIVE Qloo data (fetched for this request, cached privately on the server, never stored in the repository)"
AGE_WORDS = {"24_and_younger": "24 and younger", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44",
             "45_to_54": "45 to 54", "55_and_older": "55 and older", "35_and_younger": "35 and younger", "36_to_55": "36 to 55"}
# Our own rule for the one-word lean (not Qloo's): see README "How the lean is decided".
RISE_POINTS = 2.0       # population percentile change over the window that counts as rising / falling
WHO_MIN = 0.1           # a demographic affinity above this names a segment that leans in


class Calls:
    def __init__(self, q: Qloo):
        self.q, self.log = q, []

    def get(self, endpoint: str, params: dict) -> dict | None:
        try:
            body = self.q.get(endpoint, params)
            self.log.append({"endpoint": endpoint, "params": {k: v for k, v in params.items()}, "status": self.q.mode})
            return body
        except QlooError as e:
            self.log.append({"endpoint": endpoint, "params": params, "status": "not served" if e.unserved else "failed",
                             "http": e.status})
            return None


def _missing(c: Calls, body) -> str:
    """Why a section has nothing: the call answered without that part ("no data"), or was not served, or failed."""
    return "no data" if body is not None else c.log[-1]["status"]


def _section(status: str, **kw) -> dict:
    return {"status": status, **kw}


def _first(body: dict | None, *path):
    cur = body
    for p in path:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and isinstance(p, int) and len(cur) > p:
            cur = cur[p]
        else:
            return None
    return cur


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def drivers(expl) -> list[tuple[str, float]]:
    """(input id, score) pairs from a result's query.explainability, whatever list/dict layout it uses."""
    out: list[tuple[str, float]] = []
    if isinstance(expl, list):
        for it in expl:
            if isinstance(it, dict):
                i = it.get("entity_id") or it.get("tag_id") or it.get("id")
                s = next((_num(it.get(k)) for k in ("score", "value", "impact", "affinity") if _num(it.get(k)) is not None), None)
                if i and s is not None:
                    out.append((str(i), s))
    elif isinstance(expl, dict):
        for k, v in expl.items():
            if k == "warning":
                continue
            if _num(v) is not None:
                out.append((str(k), _num(v)))
            else:
                out.extend(drivers(v))
    return out


def resolve(c: Calls, names: list[str], types: str) -> list[dict]:
    out = []
    for n in names:
        res = _first(c.get("search", {"query": n, "types": types, "take": 1}), "results")
        hit = res[0] if isinstance(res, list) and res else None
        if isinstance(hit, dict) and hit.get("entity_id"):
            out.append({"query": n, "name": hit.get("name", n), "entity_id": hit["entity_id"]})
    return out


def build(idea: str, rivals: list[str] | None = None, location: str | None = None, q: Qloo | None = None,
          today: date | None = None, opener=None) -> dict:
    q = q or Qloo()
    p = planner.plan(idea, rivals, location, opener=opener)
    c = Calls(q)
    cat = p["category"]
    proxies = resolve(c, p["proxies"], cat)
    rival_ents = resolve(c, p["rivals"], cat)
    tags = []
    for t in p["tag_queries"]:
        got = _first(c.get("tags", {"filter.query": t, "take": 1}), "results", "tags")
        if isinstance(got, list) and got and isinstance(got[0], dict):
            tid = got[0].get("tag_id") or got[0].get("id")
            if tid:
                tags.append({"query": t, "name": got[0].get("name", t), "tag_id": tid})
    names = {e["entity_id"]: e["name"] for e in proxies + rival_ents} | {t["tag_id"]: t["name"] for t in tags}
    ent_ids = [e["entity_id"] for e in proxies]
    tag_ids = [t["tag_id"] for t in tags]
    aud = p["audience"]
    report = {"label": LIVE_LABEL if q.live else MOCK_LABEL, "mode": q.mode, "framing": FRAMING, "idea": p["idea"], "plan": p,
              "inputs": {"proxies": proxies, "rivals": rival_ents, "tags": tags},
              "made": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    signal = {"signal.interests.entities": ent_ids, "signal.interests.tags": tag_ids}
    if not ent_ids and not tag_ids:
        for s in ("who", "where", "strength", "rising", "why", "compare"):
            report[s] = _section("no input", note="Qloo search found no entity or tag for this idea; try naming a rival or a place.")
        return _finish(report, c)

    # WHY + neighbours: what this audience also likes, and which inputs drove each result (explainability)
    body = c.get("insights", {"filter.type": cat, **signal, "signal.demographics.age": aud["age"],
                              "signal.demographics.gender": aud["gender"], "take": 8})
    ents = _first(body, "results", "entities")
    if isinstance(ents, list):
        rows = []
        for e in ents[:8]:
            if not isinstance(e, dict):
                continue
            ds = sorted(drivers(_first(e, "query", "explainability")), key=lambda x: -x[1])
            rows.append({"name": e.get("name"), "entity_id": e.get("entity_id"), "affinity": _num(_first(e, "query", "affinity")),
                         "audience_growth": _num(_first(e, "query", "measurements", "audience_growth")),
                         "drivers": [{"input": names.get(i, i), "score": s} for i, s in ds[:3]]})
        agg = _first(body, "query", "explainability")
        report["why"] = _section("ok", neighbours=rows, warning=agg.get("warning") if isinstance(agg, dict) else None,
                                 source="GET /v2/insights feature.explainability=true")
    else:
        report["why"] = _section(_missing(c, body), source="GET /v2/insights feature.explainability=true")
        rows = []

    # WHO: demographic affinity of the inputs
    body = c.get("demographics", signal)
    demo = _first(body, "results", "demographics")
    if isinstance(demo, list) and demo:
        ages: dict[str, list[float]] = {}
        gender: dict[str, list[float]] = {}
        for d in demo:
            for k, v in (_first(d, "query", "age") or {}).items():
                if _num(v) is not None:
                    ages.setdefault(k, []).append(_num(v))
            for k, v in (_first(d, "query", "gender") or {}).items():
                if _num(v) is not None:
                    gender.setdefault(k, []).append(_num(v))
        segs = sorted(({"age": k, "label": AGE_WORDS.get(k, k), "score": round(sum(v) / len(v), 3)} for k, v in ages.items()),
                      key=lambda s: -s["score"])
        gen = {k: round(sum(v) / len(v), 3) for k, v in gender.items()}
        report["who"] = _section("ok", segments=segs, gender=gen, inputs=len(demo),
                                 source="GET /v2/insights filter.type=urn:demographics (mean over the inputs)")
    else:
        report["who"] = _section(_missing(c, body), source="GET /v2/insights filter.type=urn:demographics")

    # WHERE: heatmap around the place
    if p["location"]:
        body = c.get("heatmap", {"filter.location.query": p["location"], **signal})
        cells = _first(body, "results", "heatmap")
        if isinstance(cells, list) and cells:
            out = []
            for cell in cells:
                gh = _first(cell, "location", "geohash")
                lat, lon = _num(_first(cell, "location", "latitude")), _num(_first(cell, "location", "longitude"))
                if (lat is None or lon is None) and gh:
                    lat, lon = decode(gh)
                out.append({"lat": lat, "lon": lon, "geohash": gh, "affinity": _num(_first(cell, "query", "affinity")),
                            "popularity": _num(_first(cell, "query", "popularity"))})
            out.sort(key=lambda x: -(x["affinity"] or 0))
            report["where"] = _section("ok", location=p["location"], cells=out[:12],
                                       source="GET /v2/insights filter.type=urn:heatmap")
        else:
            report["where"] = _section(_missing(c, body), location=p["location"], source="GET /v2/insights filter.type=urn:heatmap")
    else:
        report["where"] = _section("no input", note="No place named: add one (for example 'in London') for the heatmap.")

    # STRENGTH vs rivals: affinity of each proxy and rival for the same audience signal (filter.results.entities)
    rival_note = None
    if not rival_ents and rows and rows[0].get("entity_id") and rows[0]["entity_id"] not in ent_ids:
        rival_ents = [{"query": None, "name": rows[0]["name"], "entity_id": rows[0]["entity_id"]}]
        rival_note = "No rival named: measured against the nearest neighbour by Qloo affinity."
    measured = [(e, "proxy") for e in proxies] + [(e, "rival") for e in rival_ents]
    if measured and tag_ids:
        body = c.get("insights", {"filter.type": cat, "signal.interests.tags": tag_ids, "signal.demographics.age": aud["age"],
                                  "signal.demographics.gender": aud["gender"],
                                  "filter.results.entities": [e["entity_id"] for e, _ in measured], "take": len(measured)})
        got = {e.get("entity_id"): _num(_first(e, "query", "affinity")) for e in (_first(body, "results", "entities") or []) if isinstance(e, dict)}
        if body is not None:
            srows = [{"name": e["name"], "entity_id": e["entity_id"], "role": role, "affinity": got.get(e["entity_id"])} for e, role in measured]
            report["strength"] = _section("ok", rows=srows, note=rival_note,
                                          source="GET /v2/insights signal.interests.tags + filter.results.entities")
        else:
            report["strength"] = _section(_missing(c, body), source="GET /v2/insights filter.results.entities")
    else:
        report["strength"] = _section("no input", note="Strength needs a resolved entity and at least one tag.")

    # RISING: trending over the last 12 weeks for the first proxy (or rival)
    anchor = (proxies or rival_ents or [None])[0]
    if anchor:
        end = today or datetime.now(timezone.utc).date()
        body = c.get("trending", {"filter.type": cat, "signal.interests.entities": [anchor["entity_id"]],
                                  "filter.start_date": (end - timedelta(days=84)).isoformat(), "filter.end_date": end.isoformat()})
        series = [r for r in (_first(body, "results", "trending") or []) if isinstance(r, dict) and _num(r.get("population_percentile")) is not None]
        if series:
            series.sort(key=lambda r: r.get("date", ""))
            change = round(series[-1]["population_percentile"] - series[0]["population_percentile"], 2)
            direction = "rising" if change >= RISE_POINTS else "falling" if change <= -RISE_POINTS else "flat"
            report["rising"] = _section("ok", entity=anchor["name"], change_points=change, direction=direction,
                                        series=[{"date": r.get("date"), "percentile": r["population_percentile"]} for r in series],
                                        source="GET /v2/trending population_percentile")
        else:
            report["rising"] = _section(_missing(c, body), entity=anchor["name"], source="GET /v2/trending")
    else:
        report["rising"] = _section("no input", note="Trending needs a resolved entity.")

    # COMPARE: the proxies' audience against the rivals' (Qloo's analysis/compare)
    if proxies and rival_ents:
        body = c.get("compare", {"a.signal.interests.entities": [e["entity_id"] for e in proxies],
                                 "b.signal.interests.entities": [e["entity_id"] for e in rival_ents], "take": 6})
        items = _first(body, "results")
        if isinstance(items, dict):
            items = items.get("entities") or items.get("tags") or []
        if isinstance(items, list):
            report["compare"] = _section("ok", items=[{"name": i.get("name"), "id": i.get("entity_id") or i.get("tag_id")}
                                                      for i in items[:6] if isinstance(i, dict)],
                                         source="GET /v2/analysis/compare")
        else:
            report["compare"] = _section(_missing(c, body), source="GET /v2/analysis/compare")
    else:
        report["compare"] = _section("no input", note="Compare needs a resolved proxy and a rival.")
    return _finish(report, c)


def lean(r: dict) -> dict:
    """Our own one-word reading of the sections (rule in the README); never a forecast."""
    points, used, why = 0, 0, []
    s = r.get("strength", {})
    vals = [x for x in s.get("rows", []) if x.get("affinity") is not None]
    prox = [x["affinity"] for x in vals if x["role"] == "proxy"]
    riv = [x["affinity"] for x in vals if x["role"] == "rival"]
    if prox and riv:
        used += 1
        if max(prox) >= max(riv):
            points += 1
            why.append("the idea's proxy scores at or above its strongest rival for this audience")
        else:
            points -= 1
            why.append("a rival scores above the idea's proxy for this audience")
    ri = r.get("rising", {})
    if ri.get("status") == "ok":
        used += 1
        points += {"rising": 1, "falling": -1}.get(ri["direction"], 0)
        why.append(f"trend over 12 weeks: {ri['direction']} ({ri['change_points']:+} percentile points)")
    w = r.get("who", {})
    if w.get("status") == "ok" and w.get("segments"):
        used += 1
        top = w["segments"][0]
        if top["score"] > WHO_MIN:
            points += 1
            why.append(f"a clear audience leans in: ages {top['label']} ({top['score']:+})")
        else:
            why.append("no age segment leans in clearly")
    if used < 2:
        word = "insufficient evidence"
    else:
        word = "leans wanted" if points >= 2 else "mixed" if points >= 0 else "weak"
    return {"word": word, "points": points, "sections_used": used, "why": why}


def _finish(report: dict, c: Calls) -> dict:
    report["calls"] = c.log
    report["lean"] = lean(report)
    body = json.dumps({k: v for k, v in report.items() if k not in ("made",)}, sort_keys=True, default=str)
    report["hash"] = hashlib.sha256(body.encode()).hexdigest()
    return report
