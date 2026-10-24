"""The Qloo client: mode and label, no personal data out, bounded retries, a minimal live-only cache, and no key
anywhere in what it writes or returns."""
import json

import pytest

from knos_wanted import privacy, qloo_mcp
from knos_wanted.qloo_mcp import InProcess, Qloo, QlooUnavailable


def test_mock_mode_is_labelled(q):
    assert q.mode == "mock" and q.label == qloo_mcp.MOCK_LABEL
    st = q.status()
    assert st["aggregate"] == "aggregate taste, not a prediction about one person" and len(st["tools"]) == 10
    trail = []
    q.call("qloo_find_tags", {"query": "coffee", "limit": 2}, why="test", trail=trail)
    assert trail[0]["label"] == qloo_mcp.MOCK_LABEL and trail[0]["tool"] == "qloo_find_tags" and trail[0]["request"] == {"query": "coffee", "limit": 2}


def test_force_mock_without_node(monkeypatch):
    monkeypatch.setattr(qloo_mcp.Bridge, "available", staticmethod(lambda: "Node.js is not installed"))
    c = Qloo(sleep=lambda s: None)
    assert c.mode == "mock" and isinstance(c.t, InProcess) and c.reason == "KNOS_WANTED_MOCK=1"


def test_no_credential_means_mock(monkeypatch):
    """`qloo mcp` started but qloo_capabilities says adapter.ready false (no key): Knos falls back to MOCK, labelled."""
    monkeypatch.delenv("KNOS_WANTED_MOCK")

    class NotReady(qloo_mcp.Bridge):
        def init(self):
            if self.mock:
                return InProcess().init()
            return {"server": {"name": "qloo-harness"}, "tools": [], "capabilities": {"adapter": {"ready": False}}}

        def call(self, name, arguments):
            return InProcess().call(name, arguments)

    class NotReadyDirect:                           # the live path: `qloo mcp` spoken to directly (qloo_mcp.Direct)
        def __init__(self, *a, **k):
            pass

        def init(self):
            return {"server": {"name": "qloo-harness"}, "tools": [], "capabilities": {"adapter": {"ready": False}}}

        def close(self):
            pass

    monkeypatch.setattr(qloo_mcp, "Bridge", NotReady)
    monkeypatch.setattr(qloo_mcp, "Direct", NotReadyDirect)
    monkeypatch.setattr(NotReady, "available", staticmethod(lambda: None))
    monkeypatch.setattr(qloo_mcp.shutil, "which", lambda name: "/usr/bin/" + name)
    c = Qloo(sleep=lambda s: None)
    assert c.mode == "mock" and "adapter.ready false" in c.reason


def test_personal_data_never_leaves(q):
    calls = []
    q.t.call = lambda name, args: calls.append(name)
    for bad in ("jane@example.com", "+44 7700 900123", "@janedoe", "https://x.com/jane", "my name is Jane", "12 Baker Street"):
        with pytest.raises(privacy.PersonalData):
            q.call("qloo_describe", {"entity": bad}, why="test")
    assert calls == []


def test_ids_and_dates_are_not_personal_data():
    privacy.check({"entities": ["5B4A9B3C-1E5F-4C7B-9C3A-2B1D0E9F8A76", "urn:tag:genre:place:cafe", "mock-brand-x-a"],
                   "start_date": "2026-07-22"})


def test_bounded_retries_only_when_retryable():
    slept = []
    c = Qloo(InProcess(fail="qloo_rank:QLOO_RATE_LIMIT:retryable:2,qloo_trends:QLOO_AUTH:fatal:5"), mode="mock", sleep=slept.append)
    trail = []
    env = c.call("qloo_rank", {"options": ["mock-brand-a-a"], "option_type": "brand", "signals": ["mock-brand-b-a"]}, why="t", trail=trail)
    assert env["status"] == "ok" and trail[-1]["attempts"] == 3 and slept == list(qloo_mcp.BACKOFF_S)
    env = c.call("qloo_trends", {"entities": ["mock-brand-a-a"], "entity_type": "brand", "start_date": "2026-01-01", "end_date": "2026-02-01"},
                 why="t", trail=trail)
    assert env["status"] == "error" and trail[-1]["attempts"] == 1 and trail[-1]["error"] == "QLOO_AUTH"
    c3 = Qloo(InProcess(fail="qloo_rank:QLOO_RATE_LIMIT:retryable:9"), mode="mock", sleep=lambda s: None)
    env = c3.call("qloo_rank", {"options": ["mock-brand-a-a"], "option_type": "brand", "signals": ["mock-brand-b-a"]}, why="t", trail=trail)
    assert env["status"] == "error" and trail[-1]["attempts"] == 1 + qloo_mcp.RETRIES


def test_transport_failure_is_an_error_not_a_crash(q):
    def down(name, args):
        raise QlooUnavailable("the bridge stopped")
    q.t.call = down
    trail = []
    env = q.call("qloo_find_tags", {"query": "x"}, why="t", trail=trail)
    assert env["status"] == "error" and trail[0]["attempts"] == 2 and trail[0]["error"] == "TRANSPORT"


def test_cache_live_only_short_and_keyless(tmp_path, monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "qk-test-not-a-real-key-0000")
    clock = [1000.0]
    live = Qloo(InProcess(), mode="live", cache_dir=tmp_path / "c", sleep=lambda s: None, now=lambda: clock[0])
    n = []
    real = live.t.call
    live.t.call = lambda name, args: (n.append(name), real(name, args))[1]
    trail = []
    a = live.call("qloo_find_tags", {"query": "jazz"}, why="t", trail=trail)
    b = live.call("qloo_find_tags", {"query": "jazz"}, why="t", trail=trail)
    assert a == b and len(n) == 1 and trail[1]["cached"] is True
    files = list((tmp_path / "c").glob("*.json"))
    assert len(files) == 1 and "qk-test" not in files[0].read_text(encoding="utf-8") and "qk-test" not in json.dumps(trail)
    import os
    os.utime(files[0], (clock[0] - qloo_mcp.CACHE_TTL_S - 5, clock[0] - qloo_mcp.CACHE_TTL_S - 5))
    live.call("qloo_find_tags", {"query": "jazz"}, why="t", trail=trail)
    assert len(n) == 2                                       # expired: asked again
    live.call("qloo_describe", {"entity": "Jazz Cafe"}, why="t", trail=trail)   # needs_input: never cached
    assert len(list((tmp_path / "c").glob("*.json"))) == 1


def test_mock_is_never_cached(q, tmp_path):
    q.cache_dir = tmp_path / "m"
    q.call("qloo_find_tags", {"query": "jazz"}, why="t")
    assert not (tmp_path / "m").exists()


def test_only_the_nine_workflows(q):
    with pytest.raises(ValueError):
        q.call("qloo_capabilities", {}, why="t")


def test_candidates_reader():
    env = {"status": "needs_input", "resolution": {"issues": [{"input": "Nike", "candidates": [{"id": "E1", "name": "Nike", "type": "urn:entity:brand"}]}]}}
    assert qloo_mcp.candidates(env) == [{"id": "E1", "name": "Nike", "type": "urn:entity:brand", "input": "Nike", "description": None}]
    ok = {"status": "ok", "resolution": {"outcomes": [{"input": "Nike", "selected": {"id": "E1", "name": "Nike"},
                                                        "alternatives": [{"id": "E2", "name": "Nike SB"}]}]}, "results": []}
    assert [c["id"] for c in qloo_mcp.candidates(ok)] == ["E1", "E2"]
    assert qloo_mcp.results({"status": "ok", "results": {"entities": [1]}}) == [1]
    assert qloo_mcp.results({"status": "error", "results": [1]}) == []
