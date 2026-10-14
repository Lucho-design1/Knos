"""Idea in plain English -> a query plan: which Qloo category, which proxy entities and tags stand for the idea,
which rivals to measure it against, which audience and which place.

Two planners, same output (validated by `check`):
  deterministic  (default) keyword rules, no key, no network: the app runs anywhere;
  llm            any OpenAI-compatible chat endpoint (KNOS_WANTED_LLM_BASE_URL + KNOS_WANTED_LLM_API_KEY +
                 KNOS_WANTED_LLM_MODEL); its answer is validated, and on any error the deterministic plan is used.
The LLM only proposes search words. Every number in the report comes from Qloo (or the labelled mock).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

# Qloo /v2/insights filter.type values in both the hackathon guide and the Insights API reference (QLOO_SOURCES.md)
CATEGORIES = ["urn:entity:brand", "urn:entity:place", "urn:entity:artist", "urn:entity:book", "urn:entity:movie",
              "urn:entity:podcast", "urn:entity:tv_show", "urn:entity:person", "urn:entity:destination"]
AGES = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]

DOMAINS = [  # (keywords, category)
    (("cafe", "café", "coffee", "restaurant", "bar", "bakery", "gym", "studio", "shop", "store", "salon", "venue", "club",
      "hotel", "kitchen", "eatery", "brewery", "food truck", "pop-up"), "urn:entity:place"),
    (("podcast", "episode", "audio show"), "urn:entity:podcast"),
    (("book", "novel", "zine", "comic", "magazine", "newsletter"), "urn:entity:book"),
    (("film", "movie", "documentary"), "urn:entity:movie"),
    (("series", "tv show", "sitcom"), "urn:entity:tv_show"),
    (("band", "album", "music", "label", "festival", "concert", "playlist"), "urn:entity:artist"),
    (("trip", "tour", "travel", "retreat", "holiday", "getaway"), "urn:entity:destination"),
]
AUDIENCE = [  # (words, ages, gender)
    (("student", "students", "gen z", "teen", "teens", "college", "young"), ["24_and_younger", "25_to_29"], None),
    (("millennial", "millennials", "young professionals", "graduates"), ["25_to_29", "30_to_34"], None),
    (("parent", "parents", "families", "family", "moms", "dads", "mothers", "fathers"), ["30_to_34", "35_to_44"], None),
    (("retiree", "retirees", "seniors", "older", "grandparents"), ["55_and_older"], None),
    (("women", "woman", "female", "her"), None, "female"),
    (("men", "man", "male", "him"), None, "male"),
]
STOP = set("""a an the and or but for with without to of in on at by from into onto over under about as is are be been
being it its this that these those i we you they he she my our your their me us them who whom which what when where why
how not no yes so very just can could would should will shall may might must do does did done have has had having
make makes making made new idea app product service brand something thing things people want wants like kind sort
online local near using use based help helps platform company startup business offer offering sell sells selling buy
everyone anyone someone city town""".split())


class PlanError(ValueError):
    pass


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'\-]+", text.lower())


def _names(text: str) -> list[str]:
    return [n.strip(" .") for n in re.split(r",|\band\b|/|;", text) if n.strip(" .")]


def deterministic(idea: str, rivals: list[str] | None = None, location: str | None = None) -> dict:
    text = " ".join(idea.split())
    if not 3 <= len(text) <= 500:
        raise PlanError("describe the idea in 3 to 500 characters")
    low = text.lower()
    category = "urn:entity:brand"
    for keys, cat in DOMAINS:
        if any(re.search(r"\b" + re.escape(k) + r"\b", low) for k in keys):
            category = cat
            break
    found_rivals = list(rivals or [])
    m = re.search(r"(?:rivals?|competitors?|competes? with|vs\.?|versus|alternative to|like)\s*:?\s+([^.;!?]+)", text, re.I)
    if m and not found_rivals:
        found_rivals = _names(re.split(r"\b(?:for|in|but|that|which)\b", m.group(1))[0])[:3]
    if not location:
        m = re.search(r"\b(?:in|across|around)\s+((?:[A-Z][\w'\-]*\s?){1,3})", text)
        location = m.group(1).strip() if m else None
    ages: list[str] = []
    gender = None
    for words, a, g in AUDIENCE:
        if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words):
            for x in a or []:
                if x not in ages:
                    ages.append(x)
            gender = gender or g
    skip = {w.lower() for r in found_rivals for w in _words(r)} | {w.lower() for w in _words(location or "")}
    content = [w for w in _words(text) if w not in STOP and len(w) >= 4 and w not in skip]
    seen: list[str] = []
    for w in content:
        if w not in seen:
            seen.append(w)
    tag_queries = seen[:3] or ["lifestyle"]
    phrase = " ".join(seen[:2]) if len(seen) >= 2 else (seen[0] if seen else text[:40])
    return check({"idea": text, "category": category, "proxies": [phrase], "rivals": found_rivals[:3],
                  "tag_queries": tag_queries, "audience": {"age": ages[:3], "gender": gender},
                  "location": location, "planner": "deterministic (keyword rules)"})


def check(plan: dict) -> dict:
    """Validate and normalise a plan from either planner."""
    if not isinstance(plan, dict):
        raise PlanError("plan is not an object")
    out = {"idea": str(plan.get("idea", ""))[:500], "planner": str(plan.get("planner", ""))[:80]}
    cat = plan.get("category")
    out["category"] = cat if cat in CATEGORIES else "urn:entity:brand"

    def strs(v, n, ln=60):
        if isinstance(v, str):
            v = [v]
        return [s.strip()[:ln] for s in (v or []) if isinstance(s, str) and s.strip()][:n]

    out["proxies"] = strs(plan.get("proxies"), 3)
    out["rivals"] = strs(plan.get("rivals"), 3)
    out["tag_queries"] = strs(plan.get("tag_queries"), 4, 40)
    if not out["proxies"] and not out["tag_queries"]:
        raise PlanError("the plan names no proxy and no tag")
    aud = plan.get("audience") or {}
    out["audience"] = {"age": [a for a in (aud.get("age") or []) if a in AGES][:3],
                       "gender": aud.get("gender") if aud.get("gender") in ("male", "female") else None}
    loc = plan.get("location")
    out["location"] = loc.strip()[:60] if isinstance(loc, str) and loc.strip() else None
    return out


PROMPT = """You turn a product idea into search words for a cultural taste API. Answer ONLY a JSON object:
{"category": one of %s,
 "proxies": up to 3 names of EXISTING brands/places/works whose fans are this idea's likely buyers,
 "rivals": up to 3 names of existing products this idea would compete with,
 "tag_queries": up to 4 short taste keywords (genres, cuisines, styles, interests),
 "audience": {"age": subset of %s, "gender": "male"|"female"|null},
 "location": a city or region name or null}
Do not invent numbers.""" % (CATEGORIES, AGES)


def llm(idea: str, rivals: list[str] | None = None, location: str | None = None, opener=None) -> dict:
    base, key, model = (os.environ.get("KNOS_WANTED_LLM_BASE_URL"), os.environ.get("KNOS_WANTED_LLM_API_KEY"),
                        os.environ.get("KNOS_WANTED_LLM_MODEL"))
    if not (base and key and model):
        raise PlanError("LLM planner not configured")
    user = idea + (f"\nRivals named by the founder: {', '.join(rivals)}" if rivals else "") + (f"\nPlace: {location}" if location else "")
    body = json.dumps({"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with (opener or urllib.request.urlopen)(req, timeout=30) as r:
        content = json.loads(r.read())["choices"][0]["message"]["content"]
    got = json.loads(re.sub(r"^```(?:json)?|```$", "", content.strip()).strip())
    got.update({"idea": " ".join(idea.split()), "planner": f"llm ({model})"})
    if rivals:
        got["rivals"] = rivals
    if location:
        got["location"] = location
    return check(got)


def plan(idea: str, rivals: list[str] | None = None, location: str | None = None, opener=None) -> dict:
    """The LLM plan when one is configured and answers well, else the deterministic plan (always available)."""
    if os.environ.get("KNOS_WANTED_LLM_BASE_URL"):
        try:
            return llm(idea, rivals, location, opener)
        except Exception as why:  # noqa: BLE001 - any LLM failure falls back to the rules, and says so
            p = deterministic(idea, rivals, location)
            p["planner"] += f"; LLM fell back: {type(why).__name__}"
            return p
    return deterministic(idea, rivals, location)
