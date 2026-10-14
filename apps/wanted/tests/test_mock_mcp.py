"""Knos's MOCK MCP server: the same ten tool names as `qloo mcp` (harness 0.1.26), the same envelope, always labelled
MOCK, ambiguous names answered with needs_input (so the confirm step is real), and a real MCP stdio wire format."""
import io
import json
import subprocess
import sys
from pathlib import Path

from knos_wanted import mock_mcp
from knos_wanted.qloo_mcp import WORKFLOWS

APP = Path(__file__).resolve().parents[1]
REAL_TOOLS = ["qloo_capabilities", "qloo_recommend", "qloo_rank", "qloo_describe", "qloo_where_popular", "qloo_compare_audiences",
              "qloo_entity_tags", "qloo_audience_demographics", "qloo_trends", "qloo_find_tags"]   # `qloo mcp` tools/list, 14 Oct 2026


def test_same_tool_names_as_qloo_mcp():
    assert list(mock_mcp.TOOLS) == REAL_TOOLS
    assert set(WORKFLOWS) == set(REAL_TOOLS) - {"qloo_capabilities"} and len(WORKFLOWS) == 9


def test_every_envelope_is_labelled_and_synthetic():
    env = mock_mcp.call("qloo_find_tags", {"query": "coffee", "limit": 3})
    assert env["_mock"] == mock_mcp.MOCK_LABEL and env["status"] == "ok" and env["schema_version"] == "1.0-preview.1"
    assert env["execution"]["transport"] == "mcp" and env["provenance"]["endpoint"] == "/v2/tags"
    assert all("(synthetic)" in t["name"] for t in env["results"])
    env = mock_mcp.call("qloo_rank", {"options": ["mock-brand-a-a", "mock-brand-b-a"], "option_type": "brand", "signals": ["mock-brand-c-a"]})
    assert all(r["entity_id"].startswith("mock-") and "(synthetic)" in r["name"] for r in env["results"])


def test_names_need_confirmation_ids_do_not():
    env = mock_mcp.call("qloo_describe", {"entity": "Starbucks", "type": "place"})
    assert env["status"] == "needs_input"
    issue = env["resolution"]["issues"][0]
    assert issue["input"] == "Starbucks" and issue["kind"] == "ambiguous" and len(issue["candidates"]) == 3
    cid = issue["candidates"][0]["id"]
    assert mock_mcp.call("qloo_describe", {"entity": cid})["status"] == "ok"


def test_schema_rules_of_the_real_server():
    assert mock_mcp.call("qloo_trends", {"entities": ["mock-brand-x-a"], "entity_type": "brand"})["error"]["code"] == "QLOO_INPUT"
    assert mock_mcp.call("qloo_find_tags", {"query": "x", "limit": 50})["status"] == "error"
    assert mock_mcp.call("qloo_rank", {"options": ["mock-brand-x-a"], "option_type": "brand"})["status"] == "needs_input"
    got = mock_mcp.call("qloo_rank", {"options": ["mock-brand-x-a"], "option_type": "brand", "demographic": "young women"})
    assert got["status"] == "needs_input" and "signal_location" in got["summary"]


def test_same_input_same_answer():
    a = mock_mcp.call("qloo_where_popular", {"entity": "mock-place-x-a", "within": "London", "limit": 5})
    b = mock_mcp.call("qloo_where_popular", {"entity": "mock-place-x-a", "within": "London", "limit": 5})
    assert a == b and len(a["results"]) == 5


def test_stdio_wire_format():
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "qloo_find_tags", "arguments": {"query": "jazz"}}},
             {"jsonrpc": "2.0", "id": 4, "method": "nope"}]
    out = io.StringIO()
    mock_mcp.serve(io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n"), out)
    got = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [g["id"] for g in got] == [1, 2, 3, 4]
    assert got[0]["result"]["serverInfo"]["name"] == mock_mcp.SERVER_NAME and got[0]["result"]["protocolVersion"] == "2025-06-18"
    assert len(got[1]["result"]["tools"]) == 10
    assert got[2]["result"]["structuredContent"]["_mock"] == mock_mcp.MOCK_LABEL and got[2]["result"]["isError"] is False
    assert got[3]["error"]["code"] == -32601


def test_runs_as_a_process():
    p = subprocess.run([sys.executable, "-m", "knos_wanted.mock_mcp"], input=json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n",
                       capture_output=True, text=True, cwd=APP, timeout=30)
    assert json.loads(p.stdout) == {"jsonrpc": "2.0", "id": 7, "result": {}}
