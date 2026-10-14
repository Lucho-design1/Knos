"""Tavily search, standard library only: provenance of submitted code, and fresh reading for new cheat patterns.

Live when TAVILY_API_KEY is set (POST https://api.tavily.com/search, `Authorization: Bearer <key>`); otherwise MOCK:
a local `responder` returns results in the documented shape (query, results[{title, url, content, score}],
response_time, usage{credits}) and the field `knos_mock` says so. Mock result URLs use the reserved `.invalid` domain,
so no mock result can be mistaken for a real page.

Both uses are ADVISORY. A provenance match flags a candidate for a person to look at; it never changes a verdict. A
pattern found on the web becomes a cheat rule only through rules_intake (the referee's own acceptance test).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from . import sources
from .tokenfactory import Transport, _http


@dataclass
class Search:
    query: str
    results: list[dict]
    credits: int
    latency_s: float
    mock: bool
    raw: dict = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return self.credits * sources.TAVILY_USD_PER_CREDIT

    def to_dict(self) -> dict:
        return {"query": self.query, "results": [{k: r.get(k) for k in ("title", "url", "score")} for r in self.results],
                "credits": self.credits, "latency_s": round(self.latency_s, 4), "mock": self.mock,
                **({"label": sources.MOCK} if self.mock else {})}


class Tavily:
    def __init__(self, api_key: str | None = None, *, responder: Callable[[dict], list[dict]] | None = None,
                 transport: Transport | None = None, timeout_s: float = 60.0):
        self._key = api_key if api_key is not None else os.environ.get(sources.TAVILY_KEY_ENV, "")
        self.live = bool(self._key)
        self._responder = responder
        self._transport = transport or _http
        self.timeout_s = timeout_s
        self.calls: list[Search] = []

    @property
    def mode(self) -> str:
        return "live" if self.live else "mock"

    def search(self, query: str, *, search_depth: str = "basic", max_results: int = 5,
               include_domains: list[str] | None = None) -> Search:
        body = {"query": query, "search_depth": search_depth, "max_results": max_results, "include_usage": True}
        if include_domains:
            body["include_domains"] = include_domains
        t0 = time.perf_counter()
        if self.live:
            headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
            raw = self._transport("POST", sources.TAVILY_SEARCH_URL, headers, body, self.timeout_s)
        else:
            results = self._responder(body) if self._responder else []
            raw = {"query": query, "answer": None, "images": [], "results": results, "response_time": 0.0,
                   "usage": {"credits": sources.TAVILY_CREDITS.get(search_depth, 1)}, "request_id": "mock",
                   "knos_mock": sources.MOCK}
        latency = time.perf_counter() - t0
        credits = int((raw.get("usage") or {}).get("credits") or sources.TAVILY_CREDITS.get(search_depth, 1))
        s = Search(query, list(raw.get("results") or []), credits, latency, not self.live, raw)
        self.calls.append(s)
        return s


# ---- provenance ---------------------------------------------------------------------------------------------------------

_TRIVIAL = re.compile(r"^\s*(#.*|import .*|from .* import .*|def \w+\(.*\):|return\b.*|[\]\)}\s,]*|else:|try:|pass)\s*$")


def distinctive_lines(source: str, n: int = 3, min_len: int = 40) -> list[str]:
    """The longest lines a person would have had to write (not imports, comments, bare returns or brackets)."""
    lines = {ln.strip() for ln in source.splitlines() if len(ln.strip()) >= min_len and not _TRIVIAL.match(ln)}
    return sorted(lines, key=lambda s: (-len(s), s))[:n]


def provenance(client: Tavily, source: str, *, n: int = 3) -> dict:
    """Search the web for the candidate's most distinctive lines; a result whose text holds one of them verbatim is a
    possible copy (advisory: flagged for a person, never a verdict)."""
    checked, matches = [], []
    for line in distinctive_lines(source, n):
        s = client.search(f'"{line}"', max_results=5)
        checked.append(line)
        for r in s.results:
            text = (r.get("content") or "") + (r.get("raw_content") or "")
            if line in text:
                matches.append({"line": line, "url": r.get("url"), "title": r.get("title")})
    return {"checked_lines": len(checked), "matches": matches,
            "finding": "possible copy: a person should look" if matches else "no public copy found",
            "advisory": True, "mock": not client.live}
