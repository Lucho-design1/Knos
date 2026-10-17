"""Knos's demand check on Qloo's REST API: an idea in plain words -> Qloo evidence -> a decision made by code.

    report = demand_check("A smart water bottle that reminds you to drink", place="Lagos")
    report["decision"]   {"verdict": "OPEN" | "REFUSE" | "CANNOT_DECIDE", "reasons": [...], "target_units", "reserve_units"}

The Qloo calls (every number in the report names the call that produced it, by its index in report["calls"]):
  /search (+ /entities)   the closest existing products of the idea's kind; the leader = most relevant, then most popular
  /v2/tags                the idea's own taste tags (tag search on its content words, tags of that kind)
  /v2/insights urn:demographics   WHO: age and gender affinity of the matched products (at the place, when given)
  /v2/insights urn:heatmap + urn:entity:place   WHERE: the areas and named places where that taste clusters
  /v2/insights urn:audience       audience segments ranked by affinity
  /v2/trending            weekly population percentile of the leader (Qloo's series ends ~24 Jul 2026: "data through")
  /v2/analysis/compare    the idea's other matches (a) vs the leader (b): shared taste tags = overlap; else the
                          leader's own audience segments vs the idea's (one more /v2/insights call)

The DECISION is deterministic code over those numbers (RULES below; why each threshold: docs/reference/DEMAND_CHECK.md).
No language model decides. Without Qloo (no key, the budget spent, an essential call failing) the verdict is
CANNOT_DECIDE "cannot decide: no Qloo evidence". Pre-orders never open on mock, synthetic or missing data.
Directional demand evidence, not a sales forecast; aggregate taste, not a prediction about one person.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re

from .qloo_rest import LIVE_LABEL, Client, QlooError


V = 2
KIND = "knos-demand-check"
FRAMING = "Directional demand evidence, not a sales forecast."
AGGREGATE = "aggregate taste, not a prediction about one person"
NO_EVIDENCE = "cannot decide: no Qloo evidence"
NO_MATCH = "no product in Qloo matches this idea"
OWNED = "an existing product already owns this"
SERVED = "the incumbent already serves this taste"
DATA_END = "2026-07-24"     # the newest week in Qloo's /v2/trending series (measured 16 Oct 2026)
TREND_NOTE = f"Qloo's trend data ends {DATA_END} and shows no movement for these; not counted"
TREND_TYPES = {"urn:entity:brand", "urn:entity:artist", "urn:entity:movie", "urn:entity:person", "urn:entity:podcast",
               "urn:entity:tv_show", "urn:entity:actor"}
DEFAULT_PLACE = "United States"
# The market's country code, for scoping Qloo's geography (launch cities never leave the chosen market).
COUNTRIES = {"united states": "US", "usa": "US", "us": "US", "united kingdom": "GB", "uk": "GB", "nigeria": "NG",
             "germany": "DE", "france": "FR", "japan": "JP", "canada": "CA", "australia": "AU", "india": "IN",
             "brazil": "BR", "south korea": "KR", "korea": "KR", "spain": "ES", "italy": "IT", "mexico": "MX"}


def market_country(place: str | None) -> str | None:
    return COUNTRIES.get((place or DEFAULT_PLACE).strip().lower())
AUDIENCE_TYPES = ("communities", "global_issues", "hobbies_and_interests", "investing_interests", "leisure", "life_stage",
                  "lifestyle_preferences_beliefs", "political_preferences", "professional_area", "spending_habits")
AUDIENCE_TYPES = tuple("urn:audience:" + t for t in AUDIENCE_TYPES)
NEUTRAL = 0.5          # Qloo's audience affinity when it has no signal: the list comes back flat at exactly 0.5

# The kind of product, from the idea's nouns, in this priority order (a "podcast about video games" is a podcast).
KINDS = (("urn:entity:podcast", ("podcast",)), ("urn:entity:tv_show", ("tv show", "tv series", "sitcom", "web series")),
         ("urn:entity:movie", ("film", "movie", "documentary")), ("urn:entity:book", ("book", "novel", "cookbook")),
         ("urn:entity:videogame", ("video game", "videogame", "mobile game", "game", "gaming")),
         ("urn:entity:place", ("restaurant", "cafe", "coffee shop", "coffee bar", "bar", "pub", "bakery", "hotel", "gym",
                               "salon", "venue", "bistro", "diner", "food truck", "brewery", "club")),
         ("urn:entity:artist", ("band", "album", "singer", "rapper", "musician")))
NOT_KIND = ("board game", "card game", "game night", "games night")
# Words that carry no product meaning: grammar, pitch words, and the words of an instruction to this app.
STOP = set("""a an and or but the of for to in on at by with from into onto over under about above after before as is are
was were be been being it its this that these those there here which who whom whose what when where why how all any each
every some such no not nor only own same so than too very can could will would shall should may might must do does did
done have has had having i me my we our ours you your yours he she they them their his her him one two three new brand
like just really also get gets make makes made use uses using used way ways thing things people person someone anyone
everyone idea ideas product products service services startup company business app apps platform tool tools solution
solutions market markets customer customers user users buyer buyers seller sell sells buy buys selling buying
demand target reserve release funds fund money price prices order orders preorder preorders decision decide rules rule
ignore previous instruction instructions system prompt set open close verified overwhelming guaranteed exactly clone
copy version invented invent call called named name similar better best cheaper cheap first ever kind sort type lot
lots great good amazing awesome cool nice perfect ultimate premium simple easy smart now today tomorrow please brand-new
let lets without within measure measures read reads
all-new""".split())
# Audience words in the idea, and the Qloo demographic key they name.
AUDIENCE = {"student": ("age", "24_and_younger"), "students": ("age", "24_and_younger"), "teen": ("age", "24_and_younger"),
            "teens": ("age", "24_and_younger"), "teenagers": ("age", "24_and_younger"), "gen z": ("age", "24_and_younger"),
            "young": ("age", "24_and_younger"), "millennials": ("age", "30_to_34"), "parents": ("age", "35_to_44"),
            "moms": ("gender", "female"), "mums": ("gender", "female"), "dads": ("gender", "male"),
            "kids": ("age", "35_to_44"), "children": ("age", "35_to_44"), "seniors": ("age", "55_and_older"),
            "retirees": ("age", "55_and_older"), "elderly": ("age", "55_and_older"), "older": ("age", "55_and_older"),
            "women": ("gender", "female"), "woman": ("gender", "female"), "female": ("gender", "female"),
            "girls": ("gender", "female"), "men": ("gender", "male"), "male": ("gender", "male"), "guys": ("gender", "male")}
CLONE_PHRASES = ("exactly like", "just like", "clone of", "copy of", "same as", "identical to", "knockoff of",
                 "knock-off of", "rip-off of", "replica of", "a version of")

# The decision rules. Every threshold is here, read by decide() and printed in the report.
RULES = {
    "relevance": "a Qloo product counts only when its name shares 2 content words with the idea, or 1 in its name and 1 more "
                 "in its description or tags, or 3 anywhere in its name, description and tags (content words: the idea minus filler, "
                 "pitch, instruction and kind words such as podcast); "
                 "none -> REFUSE " + NO_MATCH,
    "clone": "the leader's name is in the idea together with a clone phrase ('exactly like', 'clone of', ...) or is "
             "the idea's whole subject -> REFUSE " + OWNED,
    "informative_affinity": 0.55,     # a segment counts when its affinity is above Qloo's neutral 0.5 by this margin
    "min_informative_segments": 3,    # of the top 6 segments
    "served_overlap": 0.85,           # overlap with the leader at or above this -> REFUSE on its own (a me-too)
    "owned_overlap": 0.6,             # overlap with the leader at or above this ...
    "owned_popularity": 0.95,         # ... while the leader's Qloo popularity is at or above this -> REFUSE (owned)
    "unknown_leader_popularity": 0.9,  # no leader comparison possible and the leader is this popular -> REFUSE (owned)
    "min_compare_tags": 3,            # tag overlap is computed only when both sides have this many tags
    "contradiction": -0.3,            # the idea names an audience whose Qloo affinity is at or below this -> REFUSE;
                                      # between this and 0 it halves the target
    "falling_delta": -0.02,           # trend percentile change at or below: REFUSE (falling); a flat or missing series
    "rising_delta": 0.02,             # counts neither for nor against
    "group_confirmed": 1.2,           # the idea names a buyer group (a /v2/audiences segment) that Qloo ranks in this
    "group_refuted": 0.6,             # taste's top 20 above 0.55 -> target x 1.2; named but absent or neutral -> x 0.6
    "adjacent_affinity": 0.94,        # a recommended product (/v2/insights of the idea's kind) at or above this affinity
                                      # (top-10 recommendations measured 0.93-0.955 on 16 Oct 2026: 0.94 keeps the strongest),
    "adjacent_many": 5,               # not already matched, is adjacent demand: >= 5 -> target x 1.2,
    "adjacent_many_factor": 1.2,
    "adjacent_few": 1,                # <= 1 -> target x 0.8, else x 1
    "adjacent_few_factor": 0.8,
    "base_units": 100,
    "units_formula": "target = round10(base x (1 + 2 x strength) x (1 - overlap/2) x audience_factor x trend_factor), "
                     "strength = mean (affinity - 0.5) x 2 of the informative segments, trend_factor 1.25 rising else 1, "
                     "audience_factor = 0.5 when the named audience leans mildly away (else 1) x the buyer-group factor x the "
                     "recommendations factor (see group_* and adjacent_*), clamped to [20, 1000]; "
                     "reserve = ceil(target x (0.3 + 0.2 x overlap)) units pre-ordered before the maker is paid",
}


def _norm(w: str) -> str:
    w = w.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9\-]{1,}", (text or "").lower())


def content_words(idea: str, place: str | None = None) -> list[str]:
    drop = set(tokens(place or "")) | {w for w in AUDIENCE}
    out: list[str] = []
    for w in tokens(idea):
        if len(w) < 3 or w in STOP or w in drop or _norm(w) in out:
            continue
        out.append(_norm(w))
    return out


def kind_of(idea: str) -> str:
    low = f" {idea.lower()} "
    for nk in NOT_KIND:
        low = low.replace(nk, " ")
    for t, words in KINDS:
        if any(re.search(rf"\b{re.escape(w)}s?\b", low) for w in words):
            return t
    return "urn:entity:brand"


def kind_words() -> set[str]:
    return {_norm(x) for _, ws in KINDS for w in ws for x in w.split()}


def audience_named(idea: str) -> list[tuple[str, str, str]]:
    low = f" {idea.lower()} "
    return [(w, *AUDIENCE[w]) for w in AUDIENCE if re.search(rf"\b{re.escape(w)}\b", low)]


class _Run:
    """One check's Qloo calls, numbered so every figure can cite its source. A failed call is retried once without
    the optional parts (location, tags); its error is kept short (never Qloo's raw answer)."""

    OPTIONAL = ("signal.location.query", "signal.interests.tags", "filter.location.query")

    def __init__(self, client: Client, on_call=None):
        self.c = client
        self.calls: list[dict] = []
        self.on_call = on_call or (lambda c: None)       # the agent streams each call to the page as it happens

    def get(self, path: str, params: dict, what: str) -> tuple[dict | None, int | None]:
        tries = [params]
        light = {k: v for k, v in params.items() if k not in self.OPTIONAL}
        if light != params and not (path == "/v2/insights" and params.get("filter.type") == "urn:heatmap"):
            tries.append(light)
        err = None
        for p in tries:
            try:
                got = self.c.get(path, p)
            except QlooError as e:
                err = e
                continue
            n = len(self.calls) + 1
            self.calls.append({"n": n, "call": got["source"]["call"], "what": what, "params": got["source"]["params"],
                               "cached": got["source"]["cached"], "at": got["source"]["at"],
                               **({"note": "retried without location/tags after Qloo refused them"} if p is not params else {})})
            self.calls[-1]["body_digest"] = _digest(got["body"])
            self.on_call(self.calls[-1])
            return got["body"], n
        m = re.search(r"HTTP (\d{3})", str(err))
        short = f"Qloo could not answer this part (HTTP {m.group(1)})" if m else ("Qloo's monthly call budget is spent" if "budget" in str(err)
                                                                                   else "Qloo could not be reached")
        self.calls.append({"n": len(self.calls) + 1, "call": f"GET {path}", "what": what, "params": params, "error": short})
        self.on_call(self.calls[-1])
        return None, None


def _digest(body) -> str:
    """A short, human summary of a Qloo answer (names and scores, never the whole body)."""
    r = (body or {}).get("results") if isinstance(body, dict) else None
    if isinstance(r, list):
        return f"{len(r)} results: " + ", ".join(str(x.get("name")) for x in r[:4])
    if isinstance(r, dict):
        for k in ("entities", "tags", "audiences", "heatmap", "trending", "demographics"):
            v = r.get(k)
            if isinstance(v, list):
                names = [str(x.get("name") or x.get("date") or (x.get("location") or {}).get("geohash") or "") for x in v[:4]]
                return f"{len(v)} {k}" + (": " + ", ".join(n for n in names if n) if any(names) else "")
        if "a" in r or "b" in r:
            return f"compare: {len(r.get('a') or [])} tags on the idea's side, {len(r.get('b') or [])} on the leader's"
    return "answer received"


def _results(body) -> list:
    r = (body or {}).get("results")
    return r if isinstance(r, list) else []


def _ent(r: dict, src: int, words: list[str]) -> dict:
    p = r.get("properties") or {}
    geo = p.get("geocode") or {}
    where = ", ".join(str(x) for x in (geo.get("name"), geo.get("admin1_region"), geo.get("country_code")) if x) or p.get("address") or ""
    tag_names = " ".join(str(t.get("name") or "") for t in (r.get("tags") or [])[:40] if isinstance(t, dict))
    name_t = {_norm(p) for w in tokens(r.get("name") or "") for p in [w, *w.split("-")] if p}
    all_t = name_t | {_norm(w) for w in tokens(f"{p.get('short_description') or p.get('description') or ''} {tag_names}")}
    name_hits = sorted(name_t & set(words))
    hits = sorted(all_t & set(words))
    return {"name": r.get("name"), "id": r.get("entity_id"), "type": (r.get("types") or [None])[0], "popularity": r.get("popularity"),
            "about": (p.get("short_description") or p.get("description") or "")[:240], "located": str(where)[:120],
            "address": str(p.get("address") or "")[:160], "matched_words": hits, "name_words": name_hits,
            "relevant": len(name_hits) >= 2 or (len(name_hits) >= 1 and len(hits) >= 2) or len(hits) >= 3, "src": src}


def _dedupe(ms: list[dict]) -> list[dict]:
    seen, out = set(), []
    for m in ms:
        k = re.sub(r"[^a-z0-9]", "", (m.get("name") or "").lower())
        if m.get("id") in seen or k in seen:
            continue
        seen.update({m.get("id"), k})
        out.append(m)
    return out


def _in_place(m: dict, place: str | None) -> bool:
    if not place:
        return True
    hay = f"{m.get('located')} {m.get('address')}".lower()
    return any(t in hay for t in tokens(place) if len(t) > 2)


def _trend(run: _Run, ent: dict | None, today: dt.date) -> dict:
    """The leader's weekly population percentile over the newest 26 weeks Qloo has (one window back if empty)."""
    if not ent or ent.get("type") not in TREND_TYPES:
        return {"direction": "no movement", "why": TREND_NOTE, "counted": False}
    for back in (0, 1, 2):
        end = today - dt.timedelta(weeks=12 * back)
        start = end - dt.timedelta(weeks=12)
        body, src = run.get("/v2/trending", {"filter.type": ent["type"], "signal.interests.entities": ent["id"],
                                             "filter.start_date": start.isoformat(), "filter.end_date": end.isoformat(), "take": 50},
                            f"weekly trend of {ent['name']}")
        if src is None:
            return {"direction": "unknown", "why": "Qloo's trend call failed", "counted": False}
        pts = sorted(((p.get("date"), p.get("population_percentile"), p.get("population_rank_velocity") or 0)
                      for p in ((body or {}).get("results") or {}).get("trending") or []
                      if isinstance(p.get("population_percentile"), (int, float))), key=lambda x: x[0] or "")
        if not pts:
            continue
        delta = round(pts[-1][1] - pts[0][1], 4)
        moved = len({round(p[1], 6) for p in pts}) > 1 or any(p[2] for p in pts)
        row = {"entity": ent["name"], "from": pts[0][0], "to": pts[-1][0], "data_through": pts[-1][0], "weeks": len(pts),
               "start_percentile": round(pts[0][1], 4), "end_percentile": round(pts[-1][1], 4), "delta": delta, "src": src}
        if not moved:
            return {**row, "direction": "no movement", "counted": False,
                    "why": TREND_NOTE.replace(DATA_END, pts[-1][0])}
        d = "rising" if delta >= RULES["rising_delta"] else "falling" if delta <= RULES["falling_delta"] else "flat"
        return {**row, "direction": d, "counted": d != "flat"}
    return {"direction": "no movement", "why": TREND_NOTE, "counted": False}


def _stem(w: str) -> str:
    w = w.lower()
    for suf in ("ers", "er", "ing", "ism", "ists", "ist", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


GROUP_GENERIC = {"with", "young", "and", "professional", "enthusiast", "enthusiasts", "issues", "interests", "politically",
                 "health", "beauty", "home", "art", "arts"}


def _buyer_group(run: _Run, idea: str, every: list[dict]) -> dict | None:
    """The buyer group the idea names ("for runners", "gamers"), found in Qloo's audience list (/v2/audiences), and
    whether Qloo's ranked segments for this taste (top 20) confirm it. None when the idea names no Qloo segment."""
    low = f" {idea.lower()} "
    named = low.split(" for ", 1)[1] if " for " in low else ""         # the buyers are named after "for": "... for runners"
    stems = {_stem(w) for w in tokens(named) if len(w) > 3 and w not in STOP}
    if not stems:
        return None
    body, src = run.get("/v2/audiences", {"filter.audience.types": ",".join(AUDIENCE_TYPES), "take": 300},
                        "the named buyer group: Qloo's audience segments")
    for a in (((body or {}).get("results") or {}).get("audiences") or []):
        name = str(a.get("name") or "")
        seg = {_stem(w) for w in tokens(name) if w not in GROUP_GENERIC}
        if seg and seg & stems:
            hit = next((x for x in every if str(x.get("name") or "").lower().startswith(name.lower())), None)
            aff = hit.get("affinity") if hit else None
            ok = isinstance(aff, (int, float)) and aff > RULES["informative_affinity"]
            return {"segment": name, "id": a.get("id"), "affinity": aff, "rank": every.index(hit) + 1 if hit else None,
                    "status": "confirmed" if ok else "refuted", "src": src, "src_rank": hit.get("src") if hit else None}
    return None


def _recommend(run: _Run, kind: str, signal: dict, known: set) -> dict | None:
    """Qloo's recommendations for this taste (/v2/insights filter.type = the idea's kind): products next to the idea.
    Strong neighbours (affinity >= rules) that are not already matched are adjacent demand."""
    thin = {"backfill.cross_domain.take": "5"} if len(known) < 3 else {}    # thin matches: cross-domain backfill, not a refusal
    body, src = run.get("/v2/insights", {"filter.type": kind, "take": 10, "feature.explainability": "true", "bias.trends": "high",
                                         **thin, **signal}, "recommendations: what this audience also likes (bias.trends high"
                                         + (", cross-domain backfill)" if thin else ")"))
    if src is None:
        return None
    rows = [{"name": e.get("name"), "id": e.get("entity_id"), "affinity": (e.get("query") or {}).get("affinity"), "popularity": e.get("popularity")}
            for e in (((body or {}).get("results") or {}).get("entities") or [])[:10]]
    adj = [r for r in rows if r["id"] not in known and isinstance(r["affinity"], (int, float)) and r["affinity"] >= RULES["adjacent_affinity"]]
    return {"items": rows, "adjacent": [r["name"] for r in adj], "strong": len(adj), "src": src}


def _audience(run: _Run, signal: dict, what: str, take: int = 6) -> tuple[list[dict], int | None]:
    body, src = run.get("/v2/insights", {"filter.type": "urn:audience", "take": take, **signal}, what)
    rows = [{"name": a.get("disambiguation") or a.get("name"), "affinity": (a.get("query") or {}).get("affinity"), "src": src}
            for a in (((body or {}).get("results") or {}).get("entities") or [])[:take]]
    return rows, src


def _informative(rows: list[dict]) -> list[dict]:
    return [a for a in rows if isinstance(a.get("affinity"), (int, float)) and a["affinity"] > RULES["informative_affinity"]]


def gather(run: _Run, idea: str, place: str | None, leader: str | None, today: dt.date, exclude: set[str]) -> dict:
    ev: dict = {"persona": [], "ladder": [], "tag_families": [], "product_type": None, "words": [], "matches": [], "unrelated": [], "excluded": [], "leader": None, "tags": [],
                "who": None, "where": [], "places": [], "audiences": [], "trend": None, "versus": None, "named_audience": [], "buyer_group": None, "recommended": None, "cities": [], "price": None, "persona": [], "ladder": [], "tag_families": []}
    words = content_words(idea, place)
    ev["words"], ev["named_audience"] = words, [{"word": w, "dimension": d, "key": k} for w, d, k in audience_named(idea)]
    if not words:
        return ev
    kind = ev["product_type"] = kind_of(idea)
    q_words = [w for w in words if w not in kind_words()] or words
    query = " ".join(q_words[:5]) + (f" {place}" if place and kind == "urn:entity:place" else "")
    body, src = run.get("/search", {"query": query, "types": kind, "take": 12}, "closest existing products")
    if src is None:
        return ev
    rel = [w for w in words if w not in kind_words()] or words
    found = _dedupe([_ent(r, src, rel) for r in _results(body) if r.get("entity_id")])
    # Qloo's text search reads a long query as one phrase: when nothing relevant comes back, ask again with the idea's
    # word pairs (at most 2 more calls), keeping only what passes the same relevance gate.
    if not any(m["relevant"] for m in found) and len(q_words) > 2:
        for pair in (q_words[:2], q_words[-2:]):
            b2, s2 = run.get("/search", {"query": " ".join(pair), "types": kind, "take": 12}, "closest existing products (word pair)")
            found = _dedupe(found + [_ent(r, s2, rel) for r in _results(b2) if r.get("entity_id")]) if s2 else found
            if any(m["relevant"] for m in found):
                break
    if kind == "urn:entity:place" and place:
        found = [m for m in found if _in_place(m, place)]
    ev["excluded"] = [m for m in found if m["id"] in exclude]
    found = [m for m in found if m["id"] not in exclude]
    ev["matches"] = [m for m in found if m["relevant"]][:6]
    ev["unrelated"] = [{"name": m["name"], "why": "shares too few content words with the idea"} for m in found if not m["relevant"]][:6]
    lead = None
    if leader:
        body, s2 = run.get("/search", {"query": leader[:80], "types": kind, "take": 1}, "the named market leader")
        got = [_ent(r, s2, rel) for r in _results(body) if r.get("entity_id")]
        lead = got[0] if got else None
    if lead is None and ev["matches"]:
        lead = max(ev["matches"], key=lambda m: len(m["matched_words"]) + 2 * len(m["name_words"]) + (m.get("popularity") or 0))
    near = [m for m in ev["matches"] if lead is None or m["id"] != lead["id"]][:3]
    ev["leader"] = lead
    fams, _sf = run.get("/v2/tags/types", {"filter.parents.types": kind, "take": 10}, f"tag families Qloo keeps for {kind.split(':')[-1]}s")
    ev["tag_families"] = [t.get("type") for t in ((fams or {}).get("results") or {}).get("tag_types") or []][:8]
    body, s4 = run.get("/v2/tags", {"filter.query": " ".join(q_words[:6]), "feature.semantic_search": "true",
                                    "feature.typo_tolerance": "true", "filter.parents.types": kind,
                                    "take": 8}, "taste tags: semantic search (typo-tolerant) of the product phrase")
    if body is not None:
        for t in ((body or {}).get("results") or {}).get("tags") or []:
            if t.get("id") and t["id"] not in {x["id"] for x in ev["tags"]} and {_norm(x) for x in tokens(t.get("name"))} & set(words):
                ev["tags"].append({"name": t.get("name"), "id": t["id"], "popularity": t.get("popularity"), "src": s4})
    sig_ents = [m["id"] for m in near] or ([lead["id"]] if lead else [])
    if not sig_ents:
        return ev
    signal = {"signal.interests.entities": ",".join(sig_ents), **({"signal.location.query": place} if place else {})}
    body, s5 = run.get("/v2/insights", {"filter.type": "urn:demographics", **signal}, "who: age and gender affinity")
    demo = ((body or {}).get("results") or {}).get("demographics") or []
    q = ((demo[0] or {}).get("query") or {}) if demo else {}
    if q.get("age") or q.get("gender"):
        age, gender = q.get("age") or {}, q.get("gender") or {}
        ev["who"] = {"age": age, "gender": gender, "top_age": max(age, key=age.get) if age else None,
                     "top_gender": max(gender, key=gender.get) if gender else None, "src": s5}
    loc = place or DEFAULT_PLACE
    ents_only = {"signal.interests.entities": signal["signal.interests.entities"]}
    body, s6 = run.get("/v2/insights", {"filter.type": "urn:entity:place", "filter.location.query": loc, "take": 5, **ents_only},
                       f"where: named places in {loc} where this taste clusters")
    for r in (((body or {}).get("results") or {}).get("entities") or [])[:5]:
        p = r.get("properties") or {}
        geo = p.get("geocode") or {}
        area = ", ".join(str(x) for x in (geo.get("name"), geo.get("admin2_region") or geo.get("admin1_region")) if x)
        ev["places"].append({"name": r.get("name"), "area": area or str(p.get("address") or "")[:80], "price_level": p.get("price_level"),
                             "affinity": (r.get("query") or {}).get("affinity"), "src": s6})
    body, s7 = run.get("/v2/insights", {"filter.type": "urn:heatmap", "filter.location.query": loc, "take": 5, **ents_only},
                       f"where: map points in {loc}")
    for h in (((body or {}).get("results") or {}).get("heatmap") or [])[:5]:
        lc, hq = h.get("location") or {}, h.get("query") or {}
        ev["where"].append({"lat": lc.get("latitude"), "lon": lc.get("longitude"), "affinity": hq.get("affinity"), "src": s7})
    ev["place"] = loc
    body, s11 = run.get("/v2/insights", {"filter.type": "urn:tag", "diversify.by": "subtype", "diversify.take": "2", "take": 8, **signal},
                        "taste persona: this taste's tags, one or two per family (diversify.by=subtype)")
    ev["persona"] = [{"name": t.get("name"), "family": t.get("subtype"), "src": s11}
                     for t in (((body or {}).get("results") or {}).get("tags") or [])[:8]]
    if len(ev["matches"]) >= 2:
        ladder_ids = ",".join(m["id"] for m in ev["matches"][:6])
        body, s12 = run.get("/v2/insights", {"filter.type": kind, "filter.results.entities": ladder_ids, "take": 6, **signal},
                            "brand ladder: the matched products ranked against this taste (filter.results.entities)")
        ev["ladder"] = sorted([{"name": e.get("name"), "affinity": (e.get("query") or {}).get("affinity"), "popularity": e.get("popularity"),
                                "src": s12} for e in (((body or {}).get("results") or {}).get("entities") or [])],
                              key=lambda r: -(r["affinity"] or 0))
    every, _ = _audience(run, signal, "audience segments ranked by affinity", take=20)
    ev["audiences"] = every[:6]
    ev["buyer_group"] = _buyer_group(run, idea, every)
    if ev["buyer_group"] and ev["buyer_group"].get("id"):
        signal = {**signal, "signal.demographics.audiences": ev["buyer_group"]["id"]}       # the named group steers the later calls
    ev["price"] = price_tier(every, [p_.get("price_level") for p_ in ev["places"]])
    cc = market_country(loc)
    scope = {"filter.geocode.country_code": cc} if cc else {"filter.location.query": loc}
    body, s10 = run.get("/v2/insights", {"filter.type": "urn:entity:destination", "take": 8, "feature.explainability": "true",
                                         **scope, **ents_only}, f"launch cities: destinations in {loc} where this taste is strongest")
    for r in (((body or {}).get("results") or {}).get("entities") or []):
        geo = (r.get("properties") or {}).get("geocode") or {}
        if cc and geo.get("country_code") and geo["country_code"] != cc:
            continue                       # the launch cities stay inside the chosen market
        why = ((r.get("query") or {}).get("explainability") or {}).get("signal.interests.entities") or []
        if len(ev["cities"]) < 5:
            ev["cities"].append({"name": r.get("name"), "country": geo.get("country_code"), "affinity": (r.get("query") or {}).get("affinity"),
                                 "because": [x.get("entity_id") for x in why][:3], "src": s10})
    ev["recommended"] = _recommend(run, kind, signal, {m["id"] for m in ev["matches"]} | ({lead["id"]} if lead else set()))
    ev["trend"] = _trend(run, lead, today)
    if lead:
        ev["versus"] = _versus(run, near, lead, signal, ev["audiences"])
    return ev


def _versus(run: _Run, near: list[dict], lead: dict, signal: dict, idea_aud: list[dict]) -> dict | None:
    """Overlap with the leader: shared taste tags when both sides have enough, else shared informative segments.
    Needs at least one matched product besides the leader (else there is nothing to compare: None)."""
    if not near:
        return None
    if near:
        body, s8 = run.get("/v2/analysis/compare", {"a.signal.interests.entities": ",".join(e["id"] for e in near),
                                                    "b.signal.interests.entities": lead["id"], "take": 30}, "the idea's other matches vs the leader")
        r = (body or {}).get("results") or {}

        def names(lst):
            return {str(t.get("name")): t for t in (lst or []) if isinstance(t, dict) and t.get("name")}
        a, b = names(r.get("a")), names(r.get("b"))
        if s8 is not None and min(len(a), len(b)) >= RULES["min_compare_tags"]:
            shared = set(a) & set(b)
            return {"leader": lead["name"], "method": "shared taste tags (compare)", "overlap": round(len(shared) / min(len(a), len(b)), 3),
                    "shared": sorted(shared)[:8], "whitespace": sorted(set(a) - set(b))[:8], "leader_only": sorted(set(b) - set(a))[:8],
                    "sizes": [len(a), len(b)], "src": s8}
    loc = {k: v for k, v in signal.items() if k == "signal.location.query"}
    rows, s9 = _audience(run, {"signal.interests.entities": lead["id"], **loc}, f"the leader's ({lead['name']}) audience segments", take=6)
    mine, theirs = {a["name"] for a in _informative(idea_aud)}, {a["name"] for a in _informative(rows)}
    if s9 is None or len(mine) < RULES["min_informative_segments"] or len(theirs) < RULES["min_informative_segments"]:
        return None
    shared = mine & theirs
    return {"leader": lead["name"], "method": "shared audience segments (Qloo has too few tags to compare)",
            "overlap": round(len(shared) / min(len(mine), len(theirs)), 3), "shared": sorted(shared), "whitespace": sorted(mine - theirs),
            "leader_only": sorted(theirs - mine), "sizes": [len(mine), len(theirs)], "src": s9}


def _clone(idea: str, lead: dict | None, words: list[str]) -> str | None:
    if not lead or not lead.get("name"):
        return None
    low = idea.lower()
    name = re.sub(r"\s*\(.*?\)\s*", " ", lead["name"]).strip().lower()
    if len(name) < 3 or not re.search(rf"\b{re.escape(name)}\b", low):
        return None
    rest = [w for w in words if w not in {_norm(x) for x in tokens(name)} and w not in kind_words()]
    if any(p in low for p in CLONE_PHRASES) or len(rest) <= 1:
        return f"{OWNED}: the idea is {lead['name']} itself (popularity {lead.get('popularity') or 0:.2f})"
    return None


def decide(ev: dict, live: bool, idea: str = "") -> dict:
    """The decision, by code. `live` is False when an essential input is not real Qloo data: then nothing opens."""
    none = {"target_units": None, "reserve_units": None}
    if not live:
        return {"verdict": "CANNOT_DECIDE", "reasons": [NO_EVIDENCE], **none}
    if not ev["matches"]:
        why = f"{NO_MATCH}" + (f" (content words: {', '.join(ev['words'][:6])})" if ev["words"] else " (no content words)")
        if ev.get("unrelated"):
            why += f"; Qloo's nearest results share too few of its content words: {', '.join(u['name'] for u in ev['unrelated'][:3])}"
        return {"verdict": "REFUSE", "reasons": [why], **none}
    reasons = []
    lead, vs = ev["leader"], ev["versus"]
    c = _clone(idea, lead, ev["words"])
    if c:
        reasons.append(c)
    elif vs is None and lead and (lead.get("popularity") or 0) >= RULES["unknown_leader_popularity"]:
        reasons.append(f"{OWNED}: no comparison with {lead['name']} was possible and it is very popular "
                       f"({lead['popularity']:.2f} >= {RULES['unknown_leader_popularity']})")
    elif vs is None:
        reasons.append("no leader comparison possible: Qloo has too little on this space to show room next to "
                       f"{lead['name'] if lead else 'a leader'}")
    elif vs["overlap"] >= RULES["served_overlap"]:
        reasons.append(f"{SERVED}: {lead['name']} shares {vs['overlap']:.0%} of this taste ({vs['method']}, "
                       f">= {RULES['served_overlap']:.0%}), whatever its popularity")
    elif vs["overlap"] >= RULES["owned_overlap"] and (lead.get("popularity") or 0) >= RULES["owned_popularity"]:
        reasons.append(f"{OWNED}: {lead['name']} (popularity {lead['popularity']:.2f}) shares {vs['overlap']:.0%} "
                       f"({vs['method']}, >= {RULES['owned_overlap']:.0%})")
    info = _informative(ev["audiences"])
    if len(info) < RULES["min_informative_segments"] or not ev["who"]:
        reasons.append(f"audience too thin: {len(info)} of {len(ev['audiences'])} segments above Qloo's neutral 0.5 by "
                       f"{RULES['informative_affinity'] - NEUTRAL:.2f} (needs {RULES['min_informative_segments']})"
                       + ("" if ev["who"] else "; no demographic signal"))
    factor_a = 1.0
    for na in ev["named_audience"]:
        v = ((ev["who"] or {}).get(na["dimension"]) or {}).get(na["key"])
        if isinstance(v, (int, float)) and v <= RULES["contradiction"]:
            reasons.append(f"Qloo contradicts the stated audience: '{na['word']}' ({na['key'].replace('_', ' ')}) scores {v:+.2f} "
                           f"(<= {RULES['contradiction']})")
        elif isinstance(v, (int, float)) and v < 0:
            factor_a = 0.5
    t = ev["trend"] or {}
    if t.get("direction") == "falling":
        reasons.append(f"falling trend: {t['entity']} percentile {t['start_percentile']} -> {t['end_percentile']} "
                       f"(data through {t['data_through']})")
    if reasons:
        return {"verdict": "REFUSE", "reasons": reasons, **none}
    overlap = vs["overlap"]
    strength = sum((a["affinity"] - NEUTRAL) * 2 for a in info) / len(info)
    factor_t = 1.25 if t.get("direction") == "rising" else 1.0
    bg, rec = ev.get("buyer_group"), ev.get("recommended")
    factor_g = (RULES["group_confirmed"] if bg["status"] == "confirmed" else RULES["group_refuted"]) if bg else 1.0
    factor_r = 1.0
    if rec is not None:
        factor_r = RULES["adjacent_many_factor"] if rec["strong"] >= RULES["adjacent_many"] else RULES["adjacent_few_factor"] if rec["strong"] <= RULES["adjacent_few"] else 1.0
    factor_a = round(factor_a * factor_g * factor_r, 4)
    raw = RULES["base_units"] * (1 + 2 * strength) * (1 - overlap / 2) * factor_a * factor_t
    target = int(min(1000, max(20, round(raw / 10) * 10)))
    reserve = int(math.ceil(round(target * (0.3 + 0.2 * overlap), 6)))
    why = [f"{len(ev['matches'])} Qloo products match the idea's words ({', '.join(ev['matches'][0]['matched_words'][:4])})",
           f"audience: {len(info)} informative segments, strength {strength:.2f}",
           f"vs {vs['leader']}: overlap {overlap:.0%} ({vs['method']}); room: {', '.join(vs['whitespace'][:3]) or 'none named'}",
           (f"trend: {t.get('direction')} (data through {t.get('data_through')})" if t.get("counted") else f"trend: {t.get('why') or TREND_NOTE}")]
    if any(isinstance(((ev["who"] or {}).get(na["dimension"]) or {}).get(na["key"]), (int, float)) and
           ((ev["who"] or {}).get(na["dimension"]) or {}).get(na["key"]) < 0 for na in ev["named_audience"]):
        why.append("the stated audience leans mildly away in Qloo's demographics: target halved")
    if bg:
        why.append(f"buyer group '{bg['segment']}' (/v2/audiences) {bg['status']} by Qloo's ranked segments"
                   + (f" (rank {bg['rank']}, affinity {bg['affinity']:.2f})" if bg.get("rank") else " (not in the top 20)")
                   + f": target x {factor_g}")
    if rec is not None and factor_r != 1.0:
        why.append(f"recommendations: {rec['strong']} strong adjacent products ({', '.join(rec['adjacent'][:3]) or 'none'}): target x {factor_r}")
    return {"verdict": "OPEN", "reasons": why, "target_units": target, "reserve_units": reserve,
            "formula": f"round10({RULES['base_units']} x (1 + 2 x {strength:.3f}) x (1 - {overlap:.3f}/2) x {factor_a} x {factor_t}) = {target}; "
                       f"reserve ceil({target} x (0.3 + 0.2 x {overlap:.3f})) = {reserve}"}


def report_hash(rep: dict) -> str:
    keep = {k: v for k, v in rep.items() if k not in ("hash", "calls", "made", "fees")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


ESSENTIAL = ("closest existing products", "who:", "audience segments")


PREMIUM = ("Gourmand Fine Dining", "Boutique Hotels", "High Fashion", "Watch Collecting", "Art Collectibles", "Angel Start Up Investing",
           "Wine Enthusiast", "Real Estate")
BUDGET = ("Discount Shoppers",)
TIERS = {"budget": 1, "mid": 2, "premium": 4}       # test units per pre-ordered unit (devnet test money; a scale, not a price)


def price_tier(every: list[dict], venue_levels: list | None = None) -> dict | None:
    """The price tier from Qloo's spending-habit segments in this taste's top 20 (/v2/insights urn:audience): the best
    premium segment vs Discount Shoppers, each absent one at Qloo's neutral 0.5. Difference > +0.05 -> premium,
    < -0.05 -> budget, else mid. The tier sets the pre-order's unit price in test units (TIERS)."""
    if not every:
        return None
    aff = {str(a.get("name") or "").split(" (")[0]: a.get("affinity") for a in every if isinstance(a.get("affinity"), (int, float))}
    score = round(max(aff.get(n, NEUTRAL) for n in PREMIUM) - max(aff.get(n, NEUTRAL) for n in BUDGET), 3)
    tier = "premium" if score > 0.05 else "budget" if score < -0.05 else "mid"
    seen = [n for n in (*PREMIUM, *BUDGET) if n in aff]
    lv = sorted(v for v in (venue_levels or []) if isinstance(v, (int, float)))
    venue = lv[len(lv) // 2] if lv else None            # the venues' median price_level (1-4), the price cross-check
    return {"tier": tier, "unit_price": TIERS[tier], "score": score, "segments_seen": seen,
            "venue_price_level": venue, "venue_check": (None if venue is None else
            "agrees" if (venue >= 3) == (tier == "premium") or venue == 2 else "differs"), "src": every[0].get("src")}


EFFECTS = (("closest existing products", "relevance gate and the market leader"), ("the named market leader", "the leader to compare against"),
           ("details of", "popularity of the leader (owned-space rule)"), ("taste tags", "the idea's taste tags (shown, not counted)"),
           ("who:", "sets WHO: the age and gender to target; checks a named audience"),
           ("where: named places", "sets WHERE: named places in the launch area"), ("where: map points", "sets WHERE: map hot spots"),
           ("audience segments", "audience gate, target strength and the PRICE TIER (spending-habit segments)"),
           ("the named buyer group", "confirms or refutes the buyer group named after 'for': target x1.2 / x0.6"),
           ("launch cities", "sets WHERE: the launch cities"), ("recommendations", "adjacent demand: target x1.2 / x0.8; the brand ladder"),
           ("weekly trend", "rising or falling (not counted when Qloo's series does not move)"),
           ("the idea's other matches vs the leader", "overlap with the leader: owned/served gates, the reserve, the unserved audience"),
           ("the leader's", "overlap with the leader (audience method): owned/served gates, the reserve, the unserved audience"))


def annotate(rep: dict) -> None:
    for c in rep.get("calls") or []:
        c["effect"] = next((e for k, e in EFFECTS if c["what"].startswith(k)), "evidence")
        c["out"] = c.get("error") or c.get("body_digest") or ""


def demand_check(idea: str, place: str | None = None, leader: str | None = None, client: Client | None = None,
                 today: dt.date | None = None, exclude: list[str] | None = None, on_call=None) -> dict:
    idea = " ".join(str(idea or "").split())
    if not 8 <= len(idea) <= 500:
        raise ValueError("describe the idea in 8 to 500 characters")
    place = (" ".join(str(place).split())[:60] or None) if place else None
    leader = (" ".join(str(leader).split())[:80] or None) if leader else None
    client = client or Client()
    today = today or dt.datetime.now(dt.timezone.utc).date()
    run = _Run(client, on_call)
    ok, why = client.ready()
    empty = {"product_type": None, "words": content_words(idea, place), "matches": [], "unrelated": [], "excluded": [], "leader": None,
             "tags": [], "who": None, "where": [], "places": [], "audiences": [], "trend": None, "versus": None, "named_audience": [], "buyer_group": None, "recommended": None, "cities": [], "price": None, "persona": [], "ladder": [], "tag_families": []}
    ev = gather(run, idea, place, leader, today, set(exclude or [])) if ok else empty
    failed = [c for c in run.calls if c.get("error") and c["what"].startswith(ESSENTIAL)]
    missing = [c for c in run.calls if c.get("error") and c not in failed]
    live = ok and bool(run.calls) and not failed
    if ok and not run.calls:      # no content word: nothing to ask Qloo; that is a refusal, not missing evidence
        live = True
    decision = decide(ev, live, idea)
    if not ok:
        decision["reasons"].append(why)
    elif failed:
        decision["reasons"].append(f"{failed[0]['what']}: {failed[0]['error']}")
    for c in missing:
        decision["reasons"].append(f"missing evidence (not counted): {c['what']}: {c['error']}")
    good = [c for c in run.calls if not c.get("error")]
    label = (LIVE_LABEL + ("; partial: some calls failed" if failed or missing else "")) if good else "NO QLOO EVIDENCE"
    limits = ("Qloo states no prices, no market sizes, no B2B and no medical demand; the only price signals are venue "
              "price levels (1-4) and spending-habit segments. Pre-orders and per-use payments are how willingness to pay is proven here.")
    rep = {"v": V, "kind": KIND, "limits": limits, "idea": idea, "place": place, "leader_named": leader, "label": label,
           "framing": FRAMING, "aggregate": AGGREGATE, **ev, "decision": decision, "rules": RULES, "calls": run.calls,
           "made": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "day": today.isoformat()}
    d = rep["decision"]
    if d.get("verdict") == "OPEN":            # Qloo's evidence SETS the campaign: who, where, the price, the target and the reserve
        pr = ev.get("price") or {"tier": "mid", "unit_price": TIERS["mid"]}
        vs = ev.get("versus") or {}
        d["plan"] = {"who": {"age": (ev.get("who") or {}).get("top_age"), "gender": (ev.get("who") or {}).get("top_gender"),
                             "segments": [a["name"] for a in _informative(ev.get("audiences") or [])][:4]},
                     "where": [c["name"] + (f" ({c['country']})" if c.get("country") else "") for c in ev.get("cities") or []][:4],
                     "tier": pr["tier"], "unit_price": pr["unit_price"], "target_units": d["target_units"], "reserve_units": d["reserve_units"],
                     "escrow_target": d["target_units"] * pr["unit_price"], "escrow_reserve": d["reserve_units"] * pr["unit_price"],
                     "unserved_audience": vs.get("whitespace", [])[:5],
                     "persona": [x["name"] for x in ev.get("persona") or []][:6],
                     "ladder": [{k: r[k] for k in ("name", "affinity", "popularity")} for r in ev.get("ladder") or []][:6],
                     "venue_price_level": pr.get("venue_price_level"), "venue_check": pr.get("venue_check")}
    annotate(rep)
    rep["hash"] = report_hash(rep)
    return rep
