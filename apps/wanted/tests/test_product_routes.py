"""The project, company and OpenAPI routes over HTTP, and the MCP tools that reach them."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from knos_wanted import agent, server
from knos_wanted.qloo_mcp import InProcess, Qloo


@pytest.fixture
def app():
    state = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", state
    httpd.shutdown()


def call(base, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if r.headers.get("Content-Type", "").startswith("application/json") else raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_projects_over_http(app):
    base, _ = app
    st, t = call(base, "/api/templates")
    assert st == 200 and len(t["templates"]) == 5
    assert call(base, "/api/project", {"template": "internal_tool", "title": "Tool"})[0] == 401
    tok = call(base, "/api/auth/guest", {"label": "tester"})[1]["token"]
    st, p = call(base, "/api/project", {"template": "hardware_prototype", "title": "Board", "regulatory": ["iso13485"]}, tok)
    assert st == 200 and len(p["milestones"]) == 3 + 7
    st, got = call(base, f"/api/project?id={p['id']}")
    assert st == 200 and got["title"] == "Board"
    assert call(base, "/api/project?id=zzzzzzzzzzzz")[0] == 404
    st, sb = call(base, "/api/sandbox", {"template": "ai_model_eval"}, tok)
    assert st == 200 and sb["sandbox"] is True
    st, ref = call(base, "/api/referral", {"target": "p=" + p["id"], "wallet": "11111111111111111111111111111111"}, tok)
    assert st == 200
    req = urllib.request.Request(base + ref["link"])
    opener = urllib.request.build_opener(type("NoRedirect", (urllib.request.HTTPRedirectHandler,), {"redirect_request": lambda *a, **k: None}))
    try:
        opener.open(req, timeout=10)
    except urllib.error.HTTPError as e:
        assert e.code == 302 and e.headers["Location"] == f"/?ref={ref['code']}#projects={p['id']}"
    st, csv = call(base, f"/api/company/export?project={p['id']}&format=xero")
    assert st == 200 and csv.startswith(b"*ContactName")
    assert call(base, "/api/project/fund", {"project": p["id"], "milestone": "design", "units": 5, "account": "x"})[0] in (400, 503)


def test_openapi_and_mcp(app):
    base, state = app
    st, doc = call(base, "/openapi.json")
    assert st == 200 and doc["openapi"] == "3.1.0" and "/api/project/claim" in doc["paths"] and "/mcp" in doc["paths"]
    tools = agent.mcp(state, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"knos_templates", "knos_projects", "knos_project_open", "knos_project_claim", "knos_project_post", "knos_openapi"} <= names
    got = agent.mcp(state, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "knos_templates", "arguments": {}}})
    assert len(got["result"]["structuredContent"]["templates"]) == 5
    refused = agent.mcp(state, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                "params": {"name": "knos_project_open", "arguments": {"template": "internal_tool", "title": "x y", "session": "bad"}}})
    assert refused["result"]["isError"] is True


def test_pages_have_the_views(app):
    base, _ = app
    st, page = call(base, "/")
    assert st == 200 and b'id="v-projects"' in page and b'id="v-teams"' in page and b"/static/valley.js" in page
    st, js = call(base, "/static/valley.js")
    assert st == 200 and b"KNOS_VIEW" in js


def test_every_tool_mcp_lists_is_answered_by_a_handler(app):
    """tools/call on each name tools/list gives: a tool may refuse empty arguments, but never 'unknown tool'."""
    _, state = app
    tools = agent.mcp(state, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    assert {"knos_ready", "knos_usage", "knos_milestone_prompt"} <= {t["name"] for t in tools}
    unknown = []
    for i, t in enumerate(tools):
        got = agent.mcp(state, {"jsonrpc": "2.0", "id": 10 + i, "method": "tools/call", "params": {"name": t["name"], "arguments": {}}})
        said = json.dumps(got.get("error") or got.get("result") or {})
        if "unknown tool" in said:
            unknown.append(t["name"])
    assert not unknown, unknown
    ready = agent.mcp(state, {"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "knos_ready", "arguments": {"brief": {
        "milestones": [{"name": "Login under 300 ms", "target": "p95 under 300 ms on test_login", "verifier": {"kind": "machine", "check": "ci / test_login"},
                        "deadline_days": 7}]}}}})
    assert ready["result"]["structuredContent"]["ready"] is True
    assert "knos_ready" in agent.mcp(state, {"jsonrpc": "2.0", "id": 100, "method": "tools/call",
                                             "params": {"name": "knos_usage", "arguments": {}}})["result"]["structuredContent"]["calls"]
