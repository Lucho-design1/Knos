"""Every Qloo request is checked against Qloo's own docs before it is sent: a parameter the docs do not document for
that endpoint and filter.type stops the request with an error, and nothing goes to Qloo.

The tables (src/knos/qloo_docs/, each with the docs page and the day it was read):
  entity_type_guide.tsv       the Entity Type Parameter Guide: filter.type section -> its parameters
  insights_parameters.tsv     the Parameter Reference: each parameter and the entity types it names (none: any type)
  endpoints.tsv               the lookup, analysis and trends endpoints' own parameters
  use_case_parameters.tsv     what the use-case pages document beside them (demographics, taste analysis, compare)

A filter.type the docs list with no section of its own (urn:entity:audience) takes the parameters the docs document
for /v2/insights; a filter.type value the docs do not list at all (urn:audience) is refused.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import families as F

USE_CASES = F.GUIDE.with_name("use_case_parameters.tsv")


class InvalidParameter(ValueError):
    """A request Qloo's docs do not document: refused before it is sent."""


def _rows(path: Path) -> list[list[str]]:
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#") and "\t" in line]


@lru_cache(maxsize=1)
def _tables() -> tuple[dict, set, set, dict]:
    """(use-case parameters by route or filter.type, parameters the Reference types for no entity, every /v2/insights
    parameter the docs name, the filter.type values the docs list)."""
    uses: dict[str, set[str]] = {}
    for key, param, *_ in _rows(USE_CASES):
        uses.setdefault(key, set()).add(param)
    untyped = {r[0] for r in _rows(F.REFERENCE) if len(r) < 3 or not r[2].strip()}
    every = {r[0] for r in _rows(F.REFERENCE)} | {p for ps in F.guide().values() for p in ps} | uses.get("*", set())
    types = set(F.SECTION) | {k for k in uses if k.startswith("urn:")}
    return uses, untyped, every, types


def problems(path: str, params: dict) -> list[str]:
    """What the docs do not document in this request, in words; [] when every parameter is documented."""
    uses, untyped, every, types = _tables()
    if path == "/v2/insights":
        t = str(params.get("filter.type") or "")
        if t not in types:
            return [f"filter.type={t}: not a value docs.qloo.com lists"]
        own = uses.get(t, set()) | uses.get("*", set()) | untyped
        sectioned = bool(F.guide().get(F.SECTION.get(t, ""), set())) or t in ("urn:demographics", "urn:tag")
        out = []
        for k in params:
            ok = k in own or F.allowed(t, k) or (not sectioned and k in every)
            if not ok:
                out.append(f"{k}: not documented for filter.type={t}")
        return out
    documented = F.endpoint_params(path) | uses.get(path, set())
    if not documented:
        return [f"{path}: an endpoint the docs tables do not hold"]
    return [f"{k}: not documented for {path}" for k in params if k not in documented]


def check(path: str, params: dict) -> None:
    """Raises InvalidParameter (nothing is sent) when the request holds a parameter the docs do not document."""
    said = problems(path, params)
    if said:
        raise InvalidParameter(f"{path}: {'; '.join(said)}: not sent to Qloo")
