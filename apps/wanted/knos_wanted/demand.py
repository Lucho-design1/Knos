"""MAKER flow of Knos's demand check: an idea -> Qloo inputs the maker CONFIRMS -> a demand report inside Knos.

Qloo's recommended chain (Qloo's starter/mcp-client README, "Choose a tool chain"): resolve vague words
into Qloo ids, confirm the matches with the user, then ask the taste question. Here:

  1. start    planner words -> qloo_find_tags (taste words -> tag URNs) + qloo_describe (existing products that stand
              for the idea, and its rivals -> entity candidates). Nothing else is asked until the maker confirms.
  2. confirm  the maker picks which tag / entity each word means (only offered candidates are accepted), then:
                qloo_audience_demographics + qloo_entity_tags   who the audience is
                qloo_where_popular                              where it is strongest (around the maker's place)
                qloo_trends                                     rising or not (12 weeks, idea's proxy and rivals)
                qloo_compare_audiences                          the proxy's audience against the rivals'
                qloo_rank                                       which variant / rival fits this place and audience best
  3. the demand report, with the request-to-result trail (tool, request, chosen tag/entity, why, status).

Every number is Qloo's (or the labelled MOCK's); the lean on top is Knos's own rule (README). The report describes
aggregate taste, not a prediction about one person, and is directional demand evidence, not a sales forecast.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from . import planner, privacy
from .geo import decode
from .qloo_mcp import AGGREGATE, Qloo, candidates, num, results

FRAMING = "Directional demand evidence, not a sales forecast."
TYPE = {"urn:entity:place": "place", "urn:entity:destination": "place", "urn:entity:brand": "brand", "urn:entity:artist": "artist",
        "urn:entity:book": "book", "urn:entity:movie": "movie", "urn:entity:podcast": "podcast", "urn:entity:tv_show": "tv_show",
        "urn:entity:person": "person"}
AGE_WORDS = {"24_and_younger": "24 and younger", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44",
             "45_to_54": "45 to 54", "55_and_older": "55 and older"}
RISE_POINTS = 2.0    # percentile points over the window that count as rising / falling (our rule)
WHO_MIN = 0.1        # a demographic affinity above this names a segment that leans in (our rule)
TREND_DAYS = 84


class FlowError(ValueError):
    pass


def demographic_phrase(aud: dict) -> str | None:
    """The planner's audience as the natural-language demographic the workflows take ("young women", "millennials")."""
    ages, g = aud.get("age") or [], aud.get("gender")
    young = "24_and_younger" in ages
    if g:
        return ("young " if young else "") + ("women" if g == "female" else "men")
    if "25_to_29" in ages and "30_to_34" in ages:
        return "millennials"
    return None


def _question(kind: str, word: str, env: dict, pick: str) -> dict:
    cands = candidates(env)
    if kind == "tag":
        cands = [{"id": r.get("id"), "name": r.get("name"), "type": r.get("type")} for r in results(env) if isinstance(r, dict) and r.get("id")]
    return {"key": f"{kind}:{word}", "kind": kind, "input": word, "status": env.get("status"), "summary": env.get("summary", ""),
            "candidates": cands[:5], "pick": pick}


def start(q: Qloo, idea: str, rivals: list[str] | None = None, place: str | None = None, variants: list[str] | None = None) -> dict:
    privacy.check({"rivals": rivals or [], "place": place or "", "variants": variants or []}, "maker")
    p = planner.plan(idea, rivals, place)
    typ = TYPE.get(p["category"], "brand")
    trail: list[dict] = []
    qs = []
    for word in p["tag_queries"][:3]:
        env = q.call("qloo_find_tags", {"query": word, "limit": 5}, trail=trail, step="find the taste",
                     why=f"turn the idea's word '{word}' into Qloo tag URNs, so the maker can pick the one they mean")
        qs.append(_question("tag", word, env, "many"))
    for name in (variants or p["proxies"])[:3]:
        env = q.call("qloo_describe", {"entity": name, "type": typ}, trail=trail, step="find the proxy",
                     why=f"find the existing {typ} whose audience stands for the idea ('{name}'); the maker confirms the match")
        qs.append(_question("proxy", name, env, "one"))
    for name in p["rivals"][:3]:
        env = q.call("qloo_describe", {"entity": name, "type": typ}, trail=trail, step="find the rival",
                     why=f"resolve the rival '{name}' to one Qloo entity before measuring against it")
        qs.append(_question("rival", name, env, "one"))
    return {"id": secrets.token_hex(8), "flow": "maker", "idea": p["idea"], "plan": p, "type": typ, "place": p["location"],
            "questions": qs, "trail": trail, "mode": q.mode, "label": q.label, "aggregate": AGGREGATE}


def search(q: Qloo, s: dict, key: str, name: str) -> dict:
    """The maker did not see their match: look up another name for the same question (one more qloo_describe)."""
    privacy.check({"name": name}, "maker")
    qn = next((x for x in s["questions"] if x["key"] == key), None)
    if qn is None or qn["kind"] == "tag":
        if qn is None:
            raise FlowError("unknown question")
        env = q.call("qloo_find_tags", {"query": name, "limit": 5}, trail=s["trail"], step="find the taste",
                     why=f"the maker searched another word, '{name}'")
    else:
        env = q.call("qloo_describe", {"entity": name, "type": s["type"]}, trail=s["trail"], step=f"find the {qn['kind']}",
                     why=f"the maker searched another name, '{name}'")
    new = _question(qn["kind"], name, env, qn["pick"])
    seen = {c["id"] for c in qn["candidates"]}
    qn["candidates"] += [c for c in new["candidates"] if c["id"] not in seen]
    qn["status"], qn["summary"] = new["status"], new["summary"]
    return qn


def _chosen(s: dict, choices: dict) -> tuple[list[dict], list[dict], list[dict]]:
    tags, proxies, rivals = [], [], []
    for qn in s["questions"]:
        got = choices.get(qn["key"])
        if got in (None, "", []):
            continue
        ids = got if isinstance(got, list) else [got]
        if qn["pick"] == "one" and len(ids) > 1:
            raise FlowError(f"{qn['input']}: choose one")
        offered = {c["id"]: c for c in qn["candidates"]}
        for i in ids:
            if i not in offered:
                raise FlowError(f"{qn['input']}: choose one of the candidates Qloo returned")
            c = {**offered[i], "word": qn["input"]}
            {"tag": tags, "proxy": proxies, "rival": rivals}[qn["kind"]].append(c)
    if not proxies:
        raise FlowError("confirm at least one existing product that stands for the idea")
    return tags, proxies, rivals


def confirm(q: Qloo, s: dict, choices: dict, today: date | None = None) -> dict:
    tags, proxies, rivals = _chosen(s, choices)
    for c in tags + proxies + rivals:
        s["trail"].append({"step": "maker confirmed", "tool": None, "why": f"'{c['word']}' means {c['name']}", "chosen": c["id"],
                           "status": "confirmed", "mode": q.mode})
    typ, place, trail = s["type"], s["place"], s["trail"]
    main = proxies[0]
    pids, rids = [c["id"] for c in proxies], [c["id"] for c in rivals]
    names = {c["id"]: c["name"] for c in proxies + rivals}
    rep: dict = {"flow": "maker", "idea": s["idea"], "type": typ, "place": place, "mode": q.mode, "label": q.label,
                 "framing": FRAMING, "aggregate": AGGREGATE, "planner": s["plan"]["planner"],
                 "chosen": {"tags": [{"id": c["id"], "name": c["name"]} for c in tags],
                            "proxies": [{"id": c["id"], "name": c["name"]} for c in proxies],
                            "rivals": [{"id": c["id"], "name": c["name"]} for c in rivals]}}

    # WHO: aggregate demographics of the main proxy's audience + the concepts that characterise the proxies
    env = q.call("qloo_audience_demographics", {"entity": main["id"], "entity_type": typ, "limit": 10}, trail=trail, step="who",
                 why=f"aggregate age and gender affinity of the audience of {main['name']}")
    ages: dict[str, list[float]] = {}
    gender: dict[str, list[float]] = {}
    for d in results(env):
        qd = (d or {}).get("query") or {}
        for k, v in (qd.get("age") or {}).items():
            if num(v) is not None:
                ages.setdefault(k, []).append(num(v))
        for k, v in (qd.get("gender") or {}).items():
            if num(v) is not None:
                gender.setdefault(k, []).append(num(v))
    segs = sorted(({"age": k, "label": AGE_WORDS.get(k, k), "score": round(sum(v) / len(v), 3)} for k, v in ages.items()),
                  key=lambda x: -x["score"])
    env2 = q.call("qloo_entity_tags", {"entities": pids[:3], "entity_type": typ, "limit": 8}, trail=trail, step="who",
                  why="the taste concepts that jointly characterise the confirmed proxies")
    etags = [{"id": t.get("id"), "name": t.get("name"), "affinity": num(t.get("affinity"))} for t in results(env2) if isinstance(t, dict)]
    chosen_ids = {c["id"] for c in tags}
    rep["who"] = {"status": "ok" if segs or etags else env.get("status"), "segments": segs,
                  "gender": {k: round(sum(v) / len(v), 3) for k, v in gender.items()}, "tags": etags,
                  "tag_match": [t["name"] for t in etags if t["id"] in chosen_ids],
                  "source": "qloo_audience_demographics + qloo_entity_tags"}

    # WHERE
    if place:
        env = q.call("qloo_where_popular", {"entity": main["id"], "entity_type": typ, "within": place, "limit": 10}, trail=trail,
                     step="where", why=f"where around {place} the audience of {main['name']} is strongest")
        cells = []
        for c in results(env):
            loc, qd = (c or {}).get("location") or {}, (c or {}).get("query") or {}
            lat, lon, gh = num(loc.get("latitude")), num(loc.get("longitude")), loc.get("geohash")
            if (lat is None or lon is None) and gh:
                lat, lon = decode(gh)
            cells.append({"lat": lat, "lon": lon, "geohash": gh, "affinity": num(qd.get("affinity")), "popularity": num(qd.get("popularity"))})
        rep["where"] = {"status": "ok" if cells else env.get("status"), "place": place, "cells": cells, "source": "qloo_where_popular"}
    else:
        rep["where"] = {"status": "no input", "note": "Name a place for the heatmap and the ranking."}

    # RISING
    end = today or datetime.now(timezone.utc).date()
    ents = (pids + rids)[:5]
    env = q.call("qloo_trends", {"entities": ents, "entity_type": typ, "start_date": (end - timedelta(days=TREND_DAYS)).isoformat(),
                                 "end_date": end.isoformat(), "limit": 12}, trail=trail, step="rising",
                 why="population percentile over 12 weeks for the proxy and the rivals")
    series = []
    for sr in (env.get("series") or []) if env.get("status") in ("ok", "partial", "degraded") else []:
        pts = sorted([p for p in sr.get("points") or [] if num((p or {}).get("population_percentile")) is not None],
                     key=lambda p: p.get("date", ""))
        eid = (sr.get("entity") or {}).get("entityId")
        if pts:
            ch = round(pts[-1]["population_percentile"] - pts[0]["population_percentile"], 2)
            series.append({"id": eid, "name": names.get(eid, (sr.get("entity") or {}).get("name")), "role": "proxy" if eid in pids else "rival",
                           "change_points": ch, "direction": "rising" if ch >= RISE_POINTS else "falling" if ch <= -RISE_POINTS else "flat",
                           "points": [{"date": p.get("date"), "percentile": p["population_percentile"]} for p in pts]})
    rep["rising"] = {"status": "ok" if series else env.get("status"), "series": series, "source": "qloo_trends"}

    # VS RIVALS: compare the audiences
    if rids:
        env = q.call("qloo_compare_audiences", {"group_a": pids, "group_b": rids, "target_type": typ, "limit": 8}, trail=trail,
                     step="vs rivals", why="what the proxy's audience and the rivals' audience have in common or not")
        items = [{"name": i.get("name"), "id": i.get("entity_id") or i.get("id"), "affinity": num(i.get("affinity"))}
                 for i in results(env) if isinstance(i, dict)]
        rep["rivals"] = {"status": "ok" if env.get("status") == "ok" else env.get("status"), "items": items, "source": "qloo_compare_audiences"}
    else:
        rep["rivals"] = {"status": "no input", "note": "Name a rival to compare audiences."}

    # FIT: rank the variants and rivals for this place and audience
    options = (pids + rids)[:10]
    demo = demographic_phrase(s["plan"]["audience"])
    if place and len(options) >= 2:
        args = {"options": options, "option_type": typ, "signal_location": place, **({"demographic": demo} if demo else {})}
        env = q.call("qloo_rank", args, trail=trail, step="fit",
                     why=f"which of the idea's variants and its rivals fits the taste of {demo or 'people'} in {place} best")
        rows = []
        for i, r in enumerate(results(env)):
            eid = (r or {}).get("entity_id")
            rows.append({"rank": i + 1, "id": eid, "name": names.get(eid, r.get("name")), "role": "proxy" if eid in pids else "rival",
                         "affinity": num(r.get("affinity"))})
        rep["fit"] = {"status": "ok" if rows else env.get("status"), "rows": rows, "audience": demo, "place": place,
                      "note": "Scores from separate calls are not comparable (Qloo).", "source": "qloo_rank"}
    else:
        rep["fit"] = {"status": "no input", "note": "Ranking needs a place and at least two options (a variant or a rival)."}

    rep["trail"] = trail
    rep["lean"] = lean(rep)
    rep["made"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rep["hash"] = report_hash(rep)
    return rep


def report_hash(rep: dict) -> str:
    """sha256 of what the report says (not when it was made, not per-call ids): the pre-order terms carry it."""
    keep = {k: v for k, v in rep.items() if k not in ("made", "hash", "trail", "record", "label")}
    keep["steps"] = [{"tool": t.get("tool"), "request": t.get("request"), "status": t.get("status"), "chosen": t.get("chosen")}
                     for t in rep.get("trail", [])]
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


def lean(r: dict) -> dict:
    """Knos's one-word reading of the sections (README "How the lean is decided"); never a forecast."""
    points, used, why = 0, 0, []
    rows = [x for x in (r.get("fit") or {}).get("rows", []) if x.get("affinity") is not None]
    if any(x["role"] == "proxy" for x in rows) and any(x["role"] == "rival" for x in rows):
        used += 1
        best_p = min(x["rank"] for x in rows if x["role"] == "proxy")
        best_r = min(x["rank"] for x in rows if x["role"] == "rival")
        if best_p < best_r:
            points += 1
            why.append("a variant of the idea ranks above every rival for this place and audience (qloo_rank)")
        else:
            points -= 1
            why.append("a rival ranks above every variant of the idea for this place and audience (qloo_rank)")
    main = next((x for x in (r.get("rising") or {}).get("series", []) if x["role"] == "proxy"), None)
    if main:
        used += 1
        points += {"rising": 1, "falling": -1}.get(main["direction"], 0)
        why.append(f"{main['name']} over 12 weeks: {main['direction']} ({main['change_points']:+} percentile points, qloo_trends)")
    segs = (r.get("who") or {}).get("segments") or []
    if segs:
        used += 1
        if segs[0]["score"] > WHO_MIN:
            points += 1
            why.append(f"a clear audience leans in: ages {segs[0]['label']} ({segs[0]['score']:+}, qloo_audience_demographics)")
        else:
            why.append("no age segment leans in clearly (qloo_audience_demographics)")
    word = "insufficient evidence" if used < 2 else "leans wanted" if points >= 2 else "mixed" if points >= 0 else "weak"
    return {"word": word, "points": points, "sections_used": used, "why": why, "rule": "Knos's rule, not Qloo's (README)"}
