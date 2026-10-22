"""Qloo's REST API, called from this server only (the browser never sees the key or calls Qloo).

    c = Client()                      # key from env QLOO_API_KEY, base from env QLOO_BASE_URL
    got = c.get("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": "..."})
    got["body"]      the JSON Qloo answered
    got["source"]    {"call": "GET /v2/insights", "params": {...}, "cached": bool, "at": ...}: what every number cites

Rules this module keeps, all server side:
- the key comes from the environment (QLOO_API_KEY) only; it travels in the request header, never in a URL, a log line,
  an error message, the cache or a report;
- the base URL comes from QLOO_BASE_URL (the Dockerfile and README set Qloo's hackathon server);
- answers are cached privately on the server's disk (KNOS_WANTED_CACHE/qloo-rest, one file per sha256 of method + path +
  sorted params, 7 days), never in the repository (Qloo's rule: cache privately, never publish response bodies);
- at most 4 calls per second across the whole process (a token bucket);
- a persistent monthly call counter with a hard budget (QLOO_MONTHLY_BUDGET, default 9,000): past it, new uncached calls
  are refused with a clear error, cached answers are still served.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import qloo_harness

TTL_S = 7 * 86_400
ERROR_TTL_S = 86_400          # a 4xx answer (Qloo refused the question) is remembered for a day
RATE_PER_S = 4.0
DEFAULT_BUDGET = 9_000
TIMEOUT_S = 45.0
MAX_BYTES = 4_000_000
LIVE_LABEL = "LIVE Qloo data (Qloo REST API, read for this report, cached privately on the server for up to 7 days)"


class QlooError(RuntimeError):
    """Qloo could not answer (no key, network, HTTP error, budget). The message never contains the key."""


class NoKey(QlooError):
    pass


class BudgetExceeded(QlooError):
    pass


class _Bucket:
    """A process-wide token bucket: `rate` calls per second, bursts of at most `rate`."""

    def __init__(self, rate: float, clock=time.monotonic, sleep=time.sleep):
        self.rate, self.tokens, self.clock, self.sleep = rate, rate, clock, sleep
        self.last = clock()
        self.lock = threading.Lock()

    def take(self) -> None:
        while True:
            with self.lock:
                now = self.clock()
                self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.rate
            self.sleep(wait)


BUCKET = _Bucket(RATE_PER_S)
_COUNT_LOCK = threading.Lock()


# the parameters Qloo takes only in a JSON body (docs.qloo.com: "can only be supplied when using POST HTTP method")
POST_ONLY = ("filter.exclude.entities.query", "signal.interests.entities.query")


def cache_dir() -> Path:
    base = os.environ.get("KNOS_WANTED_CACHE") or str(Path.home() / ".cache" / "knos-demand-check")
    return Path(base) / "qloo-rest"


def cache_key(method: str, path: str, params: dict) -> str:
    items = sorted((str(k), str(v)) for k, v in (params or {}).items())
    return hashlib.sha256(json.dumps([method.upper(), path, items]).encode()).hexdigest()


def _month(ts: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts))


class Client:
    def __init__(self, key: str | None = None, base: str | None = None, folder: Path | None = None, budget: int | None = None,
                 opener=None, clock=time.time, bucket: _Bucket | None = None):
        self._key = key if key is not None else os.environ.get("QLOO_API_KEY", "")
        self.base = (base or os.environ.get("QLOO_BASE_URL", "")).rstrip("/")
        self.folder = folder or cache_dir()
        self.budget = budget if budget is not None else int(os.environ.get("QLOO_MONTHLY_BUDGET") or DEFAULT_BUDGET)
        self.opener = opener or urllib.request.urlopen
        self.harness = opener is None and key is None          # the real network only: Qloo's harness answers first
        self.clock = clock
        self.bucket = bucket or BUCKET
        self.live_calls = 0                   # uncached calls made by this client (for build/test accounting)

    # ---- state -------------------------------------------------------------------------------------------------------
    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def ready(self) -> tuple[bool, str]:
        if not self._key:
            return False, "no Qloo API key on this server"
        if not self.base.startswith("https://"):
            return False, "QLOO_BASE_URL is not set to Qloo's https API (see README)"
        return True, "ok"

    def _counter(self) -> Path:
        return self.folder / "calls.txt"

    def used(self) -> int:
        """Uncached calls this calendar month (UTC), read from the persistent counter."""
        try:
            month, n = self._counter().read_text(encoding="utf-8").split()
            return int(n) if month == _month(self.clock()) else 0
        except (OSError, ValueError):
            return 0

    def _count_one(self) -> None:
        with _COUNT_LOCK:
            n = self.used()
            if n >= self.budget:
                raise BudgetExceeded(f"Qloo monthly call budget reached ({n} of {self.budget}): new questions wait for next month; cached answers still work")
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self._counter().with_suffix(".tmp")
            tmp.write_text(f"{_month(self.clock())} {n + 1}\n", encoding="utf-8")
            os.replace(tmp, self._counter())

    def status(self) -> dict:
        ok, why = self.ready()
        return {"rest": ok, "reason": why, "calls_this_month": self.used(), "budget": self.budget, "rate_per_s": RATE_PER_S,
                "cache_ttl_days": TTL_S // 86_400}

    # ---- the call ----------------------------------------------------------------------------------------------------
    def _cached(self, k: str) -> dict | None:
        f = self.folder / k[:2] / f"{k}.qloo"
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        ttl = ERROR_TTL_S if doc.get("error") else TTL_S
        return doc if self.clock() - doc.get("t", 0) <= ttl else None

    def _store(self, k: str, body, error: str | None = None, surface: str | None = None) -> None:
        d = self.folder / k[:2]
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{k}.tmp"
        tmp.write_text(json.dumps({"t": self.clock(), "body": body, **({"error": error} if error else {}),
                                   **({"surface": surface} if surface else {})}), encoding="utf-8")
        os.replace(tmp, d / f"{k}.qloo")

    def get(self, path: str, params: dict | None = None) -> dict:
        """One Qloo call. GET, except when a parameter Qloo takes only in a JSON body is set (POST_ONLY): then POST."""
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        method = "POST" if any(k in POST_ONLY for k in params) else "GET"
        k = cache_key(method, path, params)
        src = {"call": f"{method} {path}", "params": params}
        hit = self._cached(k)
        if hit is not None and hit.get("error"):
            raise QlooError(hit["error"] + " (cached refusal)")
        if hit is not None:
            return {"body": hit["body"], "source": {**src, "cached": True, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(hit["t"])),
                                                     **({"surface": hit["surface"]} if hit.get("surface") else {})}}
        ok, why = self.ready()
        if not ok:
            raise NoKey(why)
        self._count_one()
        self.bucket.take()
        m = qloo_harness.mapped(path, params) if self.harness and method == "GET" else None
        hb = qloo_harness.harness().call(*m) if m else None
        if hb is not None:                                  # Qloo's harness asked exactly this question (kit API_ACCESS)
            self.live_calls += 1
            self._store(k, hb, surface=qloo_harness.SURFACE)
            return {"body": hb, "source": {**src, "surface": qloo_harness.SURFACE, "cached": False,
                                           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))}}
        src["surface"] = "REST API"
        headers = {"x-api-key": self._key, "Accept": "application/json", "User-Agent": "knos-demand-check/0.3.34"}
        if method == "POST":
            req = urllib.request.Request(self.base + path, data=json.dumps(params).encode(), method="POST",
                                         headers={**headers, "Content-Type": "application/json"})
        else:
            req = urllib.request.Request(self.base + path + ("?" + urllib.parse.urlencode(params) if params else ""), headers=headers)
        body = None
        for attempt in range(2):
            try:
                with self.opener(req, timeout=TIMEOUT_S) as r:
                    raw = r.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise QlooError(f"{method} {path}: answer larger than {MAX_BYTES} bytes")
                body = json.loads(raw or b"{}")
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt == 0:
                    time.sleep(1.0)
                    continue
                self.live_calls += 1
                msg = f"{method} {path}: HTTP {e.code}"     # Qloo's own error text is not passed on to users
                if e.code in (401, 403):                     # said plainly, never a silent fallback (kit docs/API_ACCESS.md)
                    msg += ": Qloo refused this server's API key (missing, wrong or expired); no Qloo data was used"
                elif e.code == 429:
                    msg += ": Qloo's rate limit for this event key was reached (after one retry); try again in a minute"
                if 400 <= e.code < 500 and e.code != 429:
                    self._store(k, None, error=msg)  # a refused question is not asked again for a day
                raise QlooError(msg) from None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                raise QlooError(f"{method} {path}: {type(e).__name__}") from None
        self.live_calls += 1
        self._store(k, body, surface="REST API")
        return {"body": body, "source": {**src, "cached": False, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))}}
