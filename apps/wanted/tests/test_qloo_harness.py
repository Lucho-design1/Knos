"""Qloo's harness first (knos_wanted.qloo_harness): a call maps only when every parameter it sends is a harness argument;
a stand-in `qloo api mcp` answers several questions in flight; a harness that stops means REST, never a guess."""
import sys
import threading
from pathlib import Path

from knos_wanted import qloo_harness as H

FAKE = r'''
import json, sys, time
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        out = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    else:
        a = m["params"]["arguments"]
        if a.get("type") == "urn:die":
            sys.exit(1)
        time.sleep(0.3 if a.get("take") == 1 else 0.0)        # a slow question must not hold back a fast one
        out = {"structuredContent": {"success": True, "results": {"echo": a}}}
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": out}), flush=True)
'''


def test_only_a_question_the_harness_can_ask_exactly_is_mapped():
    assert H.mapped("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": "E1"}) == \
        ("qloo_insights", {"type": "urn:demographics", "signal_entities": "E1"})
    assert H.mapped("/v2/insights", {"filter.type": "urn:heatmap", "filter.location.query": "US", "take": "5"})[1]["take"] == 5
    assert H.mapped("/search", {"query": "kombucha", "types": "urn:entity:brand", "take": 12})[0] == "qloo_search"
    assert H.mapped("/v2/insights", {"filter.type": "urn:tag", "diversify.by": "subtype"}) is None        # no such argument
    assert H.mapped("/search", {"query": "x", "sort_by": "match"}) is None
    assert H.mapped("/v2/trending", {"filter.type": "urn:entity:brand"}) is None and H.mapped("/v2/insights", {}) is None


def test_a_stand_in_harness_answers_questions_in_flight_and_its_stop_is_a_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("KNOS_QLOO_HARNESS", raising=False)
    script = tmp_path / "fake_mcp.py"
    script.write_text(FAKE, encoding="utf-8")
    h = H.Harness(command=[sys.executable, str(script)])
    got: dict = {}
    slow = threading.Thread(target=lambda: got.__setitem__("slow", h.call("qloo_insights", {"type": "urn:a", "take": 1})))
    slow.start()
    got["fast"] = h.call("qloo_insights", {"type": "urn:b", "take": 2})
    slow.join(5)
    assert got["fast"]["results"]["echo"]["type"] == "urn:b" and got["slow"]["results"]["echo"]["type"] == "urn:a"
    assert h.answered == 2
    assert h.call("qloo_insights", {"type": "urn:die"}) is None                 # the harness stopped: the caller asks REST
    assert h.call("qloo_insights", {"type": "urn:b"}) is None                   # and it is not asked again for a minute
    monkeypatch.setenv("KNOS_QLOO_HARNESS", "0")
    assert not h.enabled()
