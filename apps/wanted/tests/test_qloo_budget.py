"""The Qloo client keeps Qloo's own limit headers and refuses to send under 2,000 calls left in Qloo's month (unless
the run is the reserved one) or past 1,500 calls on this server's UTC day; nothing is sent when it refuses.
SYNTHETIC answers only."""
import io
import json
import time
import urllib.error

import pytest

from knos_wanted import qloo_rest
from knos_wanted.qloo_rest import Client, QlooError


class Resp(io.BytesIO):
    def __init__(self, body, headers):
        super().__init__(json.dumps(body).encode())
        self.headers = headers


class Opener:
    def __init__(self, left="49000", error=None):
        self.n, self.left, self.error = 0, left, error

    def __call__(self, req, timeout=None):
        self.n += 1
        h = {"x-month-ratelimit-limit": "50000", "x-month-ratelimit-remaining": self.left, "x-month-ratelimit-reset": "2066993.99",
             "x-second-ratelimit-remaining": "9"}
        if self.error:
            raise urllib.error.HTTPError(req.full_url, self.error, "err", h, io.BytesIO(b"{}"))
        return Resp({"results": {"entities": []}}, h)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(qloo_rest, "LIMITS", {})
    monkeypatch.setattr(qloo_rest, "TODAY", {})
    monkeypatch.delenv("KNOS_QLOO_RESERVE", raising=False)


def client(tmp_path, op):
    return Client(key="test-key-not-real", base="https://example.test", folder=tmp_path, budget=100_000, opener=op, bucket=qloo_rest._Bucket(1000.0))


def test_the_limit_headers_of_every_answer_are_kept(tmp_path):
    op = Opener()
    client(tmp_path, op).get("/search", {"query": "tea", "take": 3})
    assert qloo_rest.LIMITS["x-month-ratelimit-remaining"] == "49000" and qloo_rest.LIMITS["x-second-ratelimit-remaining"] == "9"
    assert qloo_rest.LIMITS["month_reset_at"] > qloo_rest._now()[:16]          # seconds from now, kept as a time


def test_under_2000_left_in_the_month_nothing_is_sent_unless_the_run_is_reserved(tmp_path, monkeypatch):
    op = Opener(left="1999")
    c = client(tmp_path, op)
    c.get("/search", {"query": "tea", "take": 3})                       # the answer that says 1,999 left
    with pytest.raises(QlooError, match="HTTP 429: not sent: .*under 2,000"):
        c.get("/search", {"query": "coffee", "take": 3})
    assert op.n == 1
    monkeypatch.setenv("KNOS_QLOO_RESERVE", "1")
    c.get("/search", {"query": "coffee", "take": 3})
    assert op.n == 2


def test_past_1500_calls_on_the_day_nothing_is_sent(tmp_path):
    op = Opener()
    qloo_rest._today()["calls"] = qloo_rest.DAY_CAP
    with pytest.raises(QlooError, match="1,500 calls to Qloo today"):
        client(tmp_path, op).get("/search", {"query": "tea", "take": 3})
    assert op.n == 0


def test_a_refusals_headers_are_kept_too(tmp_path, monkeypatch):
    monkeypatch.setattr(qloo_rest, "_hold", {"until": 0.0})
    with pytest.raises(QlooError):
        client(tmp_path, Opener(left="0", error=429)).get("/search", {"query": "tea", "take": 3})
    assert qloo_rest.LIMITS["x-month-ratelimit-remaining"] == "0" and qloo_rest.held(time.time()) > 0
