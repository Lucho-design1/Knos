"""What keeps the free instance (512 MB) inside its memory under load: heatmap answers trimmed to the points the app
reads, at most CHECKS_AT_ONCE demand checks at a time, and the operator's /api/ops/memory to measure it (24 Oct 2026:
three out-of-memory kills, two in champion runs)."""
from __future__ import annotations

import threading
import time

from knos_wanted import check, qloo_rest


def test_a_heatmap_keeps_its_first_points_and_says_how_many_qloo_sent():
    body = {"results": {"heatmap": [{"location": {"geohash": str(i)}} for i in range(6999)]}, "duration": 1}
    got = qloo_rest.trim(body)
    assert len(got["results"]["heatmap"]) == qloo_rest.HEATMAP_KEEP and got["results"]["heatmap_total"] == 6999
    assert got["results"]["heatmap"][0] == body["results"]["heatmap"][0] and got["duration"] == 1
    small = {"results": {"heatmap": [{"x": 1}] * 5}}
    assert qloo_rest.trim(small) is small and qloo_rest.trim({"results": {"entities": [1] * 900}})["results"]["entities"] == [1] * 900
    assert qloo_rest.trim(None) is None and qloo_rest.trim([1, 2]) == [1, 2]


def test_no_more_than_checks_at_once_run_together(monkeypatch):
    seen, lock = [], threading.Lock()

    def slow(*a, **k):
        with lock:
            seen.append(check.running[0])
        time.sleep(0.05)
        return {}

    monkeypatch.setattr(check, "_demand_check", slow)
    threads = [threading.Thread(target=check.demand_check, args=("a smart water bottle",)) for _ in range(9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == 9 and max(seen) <= check.CHECKS_AT_ONCE and check.running[0] == 0


def test_the_memory_answer_names_what_a_load_test_reads():
    from knos_wanted import server

    class S:
        reports = {"a": 1, "b": 2}
    got = server.memory_now(S())
    assert set(got) == {"rss_mb", "peak_mb", "threads", "checks_running", "checks_at_once", "reports_in_memory", "processes", "all_processes_mb"}
    assert got["reports_in_memory"] == 2 and got["checks_at_once"] == check.CHECKS_AT_ONCE and got["threads"] >= 1


def test_qloo_mcp_is_spoken_to_directly_with_no_node_bridge():
    """The live MCP flow runs `qloo mcp` itself (qloo_mcp.Direct) instead of a Node bridge that starts it: here the same
    transport drives the MOCK MCP server over stdio, and the client takes it as it takes the bridge."""
    import os
    import sys
    from pathlib import Path

    from knos_wanted import qloo_mcp
    app = str(Path(qloo_mcp.__file__).resolve().parents[1])
    env = {"PYTHONPATH": os.pathsep.join([app, os.environ.get("PYTHONPATH", "")]), "QLOO_API_KEY": ""}
    t = qloo_mcp.Direct(timeout=30, command=[sys.executable, "-m", "knos_wanted.mock_mcp"], env=env)
    try:
        info = t.init()
        assert set(qloo_mcp.WORKFLOWS) <= set(info["tools"]) and info["server"].get("name")
        got = t.call("qloo_find_tags", {"query": "hot sauce"})
        assert got["isError"] is False and isinstance(got["structuredContent"], dict)
        q = qloo_mcp.Qloo(transport=t, mode="mock")
        assert q.mode == "mock" and set(qloo_mcp.WORKFLOWS) <= set(q.tools)
    finally:
        t.close()
    assert t.h.proc is None


class _Proc:
    def __init__(self):
        self.killed = self.waited = False

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


def test_a_failed_harness_question_stops_that_process_and_never_a_newer_one():
    from knos_wanted import qloo_harness
    h = qloo_harness.Harness(command=["qloo", "api", "mcp"])
    old, new = _Proc(), _Proc()
    h.proc, h.ready = new, True                      # another thread already started a new harness
    h.stop(old)                                      # the question that failed went to the old one
    assert old.killed and old.waited and h.proc is new and h.ready and not new.killed
    h.stop(new)                                      # the current one failing: stopped, and started again next time
    assert new.killed and h.proc is None and not h.ready
