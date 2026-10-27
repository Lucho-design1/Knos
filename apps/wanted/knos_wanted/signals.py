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


EVERY = "every Qloo answer"
WORDS = {"OPEN": "Open", "REFUSE": "Not yet", "CANNOT_DECIDE": "Cannot decide"}
PROOF = "https://drexthealpha.github.io/Knos/proof/"
# a rejected option's rule, as a short code (metros.stats and lift for cities, check.gather's leader for products)
CODES = {"LOWER_LIFT": "a lower lift than the launch city", "FEW_CELLS": "fewer than 3 heatmap cells", "NO_POPULATION": "no Census population",
         "NO_MAP": "Qloo gave no heatmap, so no city can launch", "OFF_MAP": "not a metro of Qloo's heatmap", "LESS_RELEVANT": "less relevant than the leader"}


def outcome(rep: dict) -> dict:
    from . import check, metros
    d = check.decide(rep, True, rep.get("idea") or "")
    t = metros.terms(rep.get("where") or [])
    return {"label": d["verdict"], "city": t["city"] if t else None, "target": t["target"] if t else None}


def _used(rep: dict, fields: dict) -> bool:
    return any(rep.get(k) not in (None, [], {}) for k in fields)


def ablate(rep: dict) -> list[dict]:
    """For one card: each Qloo call family it used removed in turn, and every answer removed, by check.py's own rules."""
    import copy

    from . import check
    rep = {**{k: v for fields in FAMILIES.values() for k, v in fields.items()}, **rep}   # a field Qloo never filled: as removed
    before, out = outcome(rep), []
    for fam, fields in FAMILIES.items():
        if not _used(rep, fields):
            continue
        after = outcome({**copy.deepcopy(rep), **copy.deepcopy(fields)})
        out.append({"chip": rep.get("idea"), "removed": fam, "city": [before["city"], after["city"]],
                    "target": [before["target"], after["target"]], "label": [before["label"], after["label"]]})
    nothing = check.decide(rep, False, rep.get("idea") or "")
    out.append({"chip": rep.get("idea"), "removed": EVERY, "city": [before["city"], None], "target": [before["target"], None],
                "label": [before["label"], nothing["verdict"]]})
    return out


def _shown(label: str, city) -> str:
    return "REFUSE" if label == "OPEN" and not city else label        # an Open with no launch city is drawn as not yet open


def headline() -> dict | None:
    """/proof/'s ablation bar: in how many one-signal removals the city, the target or the verdict moved."""
    one = [r for r in _rows() if r["removed"] != EVERY]
    return {"n": sum(map(moved, one)), "of": len(one), "href": PROOF,
            "said": f"Removing one Qloo signal moved the city, the target or the verdict in {sum(map(moved, one))} of {len(one)} tests."} if one else None


def flip(rep: dict) -> dict:
    """What would flip the verdict the card shows: the families whose removal alone changes it (the table's rows for a
    sample chip, else the same recomputation), else whether removing every answer would."""
    from . import metros
    table = [r for r in _rows() if str(r.get("chip") or "").lower() == str(rep.get("idea") or "").lower()]
    t = metros.launch_terms(rep)
    now_v = _shown((rep.get("decision") or {}).get("verdict") or "", t and t["city"])
    if table and _shown(table[0]["label"][0], table[0]["city"][0]) != now_v:
        table = []                             # the card as served (its matches re-tied) is not the card the table read
    try:
        rows = table or ablate(rep)
    except (KeyError, TypeError):              # a recording kept without the evidence the rules read again: its own reason
        v = (rep.get("decision") or {}).get("verdict") or ""
        said = (f"What would flip this verdict: only a Qloo product matching its words could. Qloo matched none, so it stays {WORDS.get(v, v)}."
                if not rep.get("matches") else f"What would flip this verdict: not recomputed, as this recording lacks the evidence. It stays {WORDS.get(v, v)}.")
        return {"said": said, "families": [], "from": "reason"}
    shown = lambda r, i: _shown(r["label"][i], r["city"][i])  # noqa: E731
    one = [r for r in rows if r["removed"] != EVERY and shown(r, 0) != shown(r, 1)]
    every = next((r for r in rows if r["removed"] == EVERY), None)
    now = WORDS.get(shown(rows[0], 0), shown(rows[0], 0)) if rows else ""
    if one:
        names = [r["removed"].split(" (")[0] for r in one]
        named = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"
        said = f"What would flip this verdict: without Qloo's {named}, {now} becomes {WORDS.get(shown(one[0], 1), shown(one[0], 1))}."
    elif every and shown(every, 0) != shown(every, 1):
        said = f"What would flip this verdict: no single Qloo signal. Without any Qloo answer, {now} becomes {WORDS.get(shown(every, 1), shown(every, 1))}."
    else:
        said = f"What would flip this verdict: no Qloo signal. It stays {now} with any of them removed."
    return {"said": said, "families": [r["removed"] for r in one], "from": "table" if table else "recomputed"}


def rejected(rep: dict, most: int = 6) -> list[dict]:
    """The cities and products Knos did not take, each with its rule's code (CODES)."""
    from . import metros
    t, out = metros.launch_terms(rep), []
    if t:
        for m in (rep.get("terms") or {}).get("metros") or []:
            if m.get("city") != t["city"]:
                code = "FEW_CELLS" if (m.get("cells") or 0) < metros.MIN_CELLS else "NO_POPULATION" if not m.get("population") else "LOWER_LIFT"
                out.append({"name": m.get("city"), "kind": "city", "code": code})
            if len(out) >= 3:
                break
    taken = {o["name"] for o in out} | ({t["city"]} if t else set())
    for c in (rep.get("cities") or [])[:6]:
        name = c.get("name") if isinstance(c, dict) else None
        if name and name not in taken and sum(o["kind"] == "city" for o in out) < 3:
            out.append({"name": name, "kind": "city", "code": "OFF_MAP" if t else "NO_MAP"})
    lead = rep.get("leader")
    lead = lead.get("name") if isinstance(lead, dict) else lead
    for m in rep.get("matches") or []:
        name = m.get("name") if isinstance(m, dict) else None
        if name and name != lead and sum(o["kind"] == "product" for o in out) < 3:
            out.append({"name": name, "kind": "product", "code": "LESS_RELEVANT"})
    return [{**o, "why": CODES[o["code"]]} for o in out[:most]]


def gap(rep: dict) -> dict:
    """The lines a recorded card opens and closes with: the model's city beside Qloo's, /proof/'s number, the flip, the
    rejected options."""
    from . import metros
    m = rep.get("model_alone") or {}
    t = metros.launch_terms(rep)
    first = next((c.get("name") for c in rep.get("cities") or [] if isinstance(c, dict) and c.get("name")), None)
    qloo = t["city"] if t else first
    out = {"headline": headline(), "flip": flip(rep), "rejected": rejected(rep)}
    if m.get("city"):
        out["sentence"] = f"Model alone says {m['city']}. Qloo says {qloo}." if qloo else f"Model alone says {m['city']}. Qloo names no city."
    return out
