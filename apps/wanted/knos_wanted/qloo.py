"""The Qloo client: live (QLOO_API_KEY set) or MOCK (synthetic, shaped from Qloo's public docs).

Every call goes through `Qloo.get(endpoint_name, params)`. The endpoints, their paths and their parameters are the
ones Qloo documents (docs/QLOO_SOURCES.md lists each page and the date it was last updated, read 14 Oct 2026):

    search        GET /search                 query, types, take
    tags          GET /v2/tags                filter.query, take
    insights      GET /v2/insights            filter.type=urn:entity:*, signal.interests.entities|tags,
                                              signal.demographics.age|gender, filter.results.entities,
                                              feature.explainability=true, take
    demographics  GET /v2/insights            filter.type=urn:demographics + signal.interests.entities|tags
    heatmap       GET /v2/insights            filter.type=urn:heatmap + filter.location.query + signal.interests.*
    trending      GET /v2/trending            filter.type, signal.interests.entities, filter.start_date, filter.end_date
    compare       GET /v2/analysis/compare    a.signal.interests.entities, b.signal.interests.entities, take

Auth: header `X-Api-Key`; hackathon keys work only against https://hackathon.api.qloo.com (Qloo Agentic Hackathon
Developer Guide). The key is read from the environment and never logged, cached or returned.

Qloo rule: response data may be cached privately on the server, never in a public repository. The live cache
lives under KNOS_WANTED_CACHE (default .cache/qloo, git-ignored) and is never part of the repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import mock

DEFAULT_BASE = "https://hackathon.api.qloo.com"
MOCK_LABEL = "MOCK (synthetic, not real Qloo data)"

# name -> (path, fixed params). The fixed params are what makes an /v2/insights call a demographics or heatmap call.
ENDPOINTS: dict[str, tuple[str, dict[str, str]]] = {
    "search": ("/search", {}),
    "tags": ("/v2/tags", {}),
    "insights": ("/v2/insights", {"feature.explainability": "true"}),
    "demographics": ("/v2/insights", {"filter.type": "urn:demographics"}),
    "heatmap": ("/v2/insights", {"filter.type": "urn:heatmap"}),
    "trending": ("/v2/trending", {}),
    "compare": ("/v2/analysis/compare", {}),
}

# HTTP statuses that mean "this key or this environment does not serve this call": the report degrades that section.
UNSERVED = {401, 403, 404, 405, 501}


class QlooError(Exception):
    def __init__(self, endpoint: str, status: int | None, why: str):
        super().__init__(f"{endpoint}: {why}")
        self.endpoint, self.status, self.why = endpoint, status, why

    @property
    def unserved(self) -> bool:
        return self.status in UNSERVED


def _clean(params: dict[str, Any]) -> dict[str, str]:
    out = {}
    for k, v in params.items():
        if v is None or v == "" or v == []:
            continue
        out[k] = ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v).lower() if isinstance(v, bool) else str(v)
    return out


class Qloo:
    """One client for the whole app. `live` is True when QLOO_API_KEY is set (and mock was not forced)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, cache_dir: str | os.PathLike | None = None,
                 force_mock: bool | None = None, timeout: float = 15.0, opener=None, unserved: set[str] | None = None):
        if force_mock is None:
            force_mock = os.environ.get("KNOS_WANTED_MOCK", "") == "1"
        self._key = None if force_mock else (api_key if api_key is not None else os.environ.get("QLOO_API_KEY") or None)
        self.base_url = (base_url or os.environ.get("QLOO_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.cache_dir = Path(cache_dir or os.environ.get("KNOS_WANTED_CACHE") or ".cache/qloo")
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen
        # endpoints the probe found unserved for this key (knos_wanted.probe writes .cache/probe.json): skipped up front
        self.unserved = set(unserved) if unserved is not None else self._probe_unserved()

    @property
    def live(self) -> bool:
        return bool(self._key)

    @property
    def mode(self) -> str:
        return "live" if self.live else "mock"

    def _probe_unserved(self) -> set[str]:
        try:
            got = json.loads((self.cache_dir.parent / "probe.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return {name for name, r in got.get("endpoints", {}).items() if r.get("status") in UNSERVED}

    def url(self, endpoint: str, params: dict[str, Any]) -> str:
        path, fixed = ENDPOINTS[endpoint]
        q = {**fixed, **_clean(params)}
        return f"{self.base_url}{path}?{urllib.parse.urlencode(q, safe=':,')}"

    def get(self, endpoint: str, params: dict[str, Any]) -> dict:
        """The JSON body of one call. Mock mode: a synthetic body shaped from Qloo's docs, carrying "_mock"."""
        if endpoint not in ENDPOINTS:
            raise ValueError(f"unknown endpoint {endpoint!r}")
        if not self.live:
            body = mock.respond(endpoint, {**ENDPOINTS[endpoint][1], **_clean(params)})
            body["_mock"] = MOCK_LABEL
            return body
        if endpoint in self.unserved:
            raise QlooError(endpoint, 403, "not served by this key (probe)")
        url = self.url(endpoint, params)
        cached = self._cache_read(url)
        if cached is not None:
            return cached
        status, body = self.raw(url)
        if status != 200:
            raise QlooError(endpoint, status, f"HTTP {status}")
        try:
            data = json.loads(body)
        except ValueError:
            raise QlooError(endpoint, status, "the answer is not JSON") from None
        self._cache_write(url, data)
        return data

    def raw(self, url: str) -> tuple[int | None, bytes]:
        """(HTTP status, body) of a GET with the key header; (None, b"") when the network failed."""
        req = urllib.request.Request(url, headers={"X-Api-Key": self._key or "", "Accept": "application/json",
                                                   "User-Agent": "knos-wanted/0.1"})
        for attempt in range(3):
            try:
                with self._open(req, timeout=self.timeout) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return e.code, b""
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(1.0)
                    continue
                return None, b""
        return None, b""

    # -- private server-side cache (Qloo allows it; never in a public repository) ------------------------------------
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _cache_read(self, url: str) -> dict | None:
        try:
            return json.loads(self._cache_path(url).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _cache_write(self, url: str, data: dict) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            p = self._cache_path(url)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, p)
        except OSError:
            pass
