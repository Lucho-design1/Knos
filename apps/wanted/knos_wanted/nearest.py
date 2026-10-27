"""The nearest idea Qloo has already answered, for a new idea Qloo cannot answer now. Computed here, offline, with no
Qloo call: both ideas lowercased, English stop words dropped, each word reduced to its stem (check._stem), then the
new idea's stems found in the answered idea's own words or in the names of the Qloo tags its report holds are counted.
The highest count wins; a tie goes to the newest answer. Under 2, no answered idea is near enough: the 3 nearest are
offered instead. The answered reports are the recordings (recorded.py), kept privately."""
from __future__ import annotations

import re

from .check import _stem

MIN_SHARED = 2
OFFER = 3
# English stop words (function words only: the idea's own nouns, such as "app" or "brand", still count)
ENGLISH_STOP = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her here
hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once
only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we were what when where which while who whom why
will with would you your yours yourself yourselves""".split())


def stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[^\W\d_]+", str(text or "").lower()) if w not in ENGLISH_STOP}


def shared(idea: str, rep: dict) -> int:
    """How many of the new idea's stems appear in the answered idea's words or its Qloo tags' names."""
    theirs = stems(rep.get("idea") or "")
    for t in rep.get("tags") or []:
        theirs |= stems(t.get("name") if isinstance(t, dict) else t)
    return len(stems(idea) & theirs)


def rank(idea: str, answered: list[dict]) -> list[tuple[int, dict]]:
    """Every answered report with its count, the nearest first (ties: the newest first)."""
    scored = [(shared(idea, r), r) for r in answered]
    return sorted(scored, key=lambda x: (x[0], str(x[1].get("made") or "")), reverse=True)


def find(idea: str, answered: list[dict]) -> dict | None:
    """{"report", "count", "next"} when the nearest shares at least MIN_SHARED stems (next: the 3 after it); else
    {"options": the 3 nearest}. An answered idea that shares no stem with this one is nobody's neighbour: it is never
    offered, so two ideas with nothing in common with the answers get no options, not the same newest three."""
    ranked = rank(idea, answered)
    if not ranked:
        return None
    n, best = ranked[0]
    near = [str(r.get("idea") or "") for c, r in ranked if c >= 1]
    if n >= MIN_SHARED:
        return {"report": best, "count": n, "next": near[1:1 + OFFER]}
    return {"options": near[:OFFER], "count": n}
