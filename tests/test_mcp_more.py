"""`knos mcp` beyond tools (src/knos/mcp_more.py, MCP 2026-07-28): resources and resource templates, prompts, an
output schema on every tool, and a person's confirmation (elicitation through a multi-round-trip request) before a
tool posts to GitHub as their account."""
from __future__ import annotations

import io
import json

import pytest
from solders.pubkey import Pubkey

from test_agentkey import ISSUE, acting, world as agent_world  # noqa: F401 - the fixture
from test_mcp import talk, world

from knos import mcp, mcp_more

META = {"_meta": {mcp.VERSION_KEY: mcp.PROTOCOL}}
ELICIT = {"_meta": {mcp.VERSION_KEY: mcp.PROTOCOL, mcp_more.CAPS_KEY: {"elicitation": {"form": {}}}}}


def rpc(method: str, params: dict | None = None, ledger=None, github=None) -> dict:
    (reply,) = talk([{"jsonrpc": "2.0", "id": 1, "method": method, "params": {**META, **(params or {})}}], ledger, github)
    return reply


def test_resources_and_templates_are_listed_with_their_cache_lifetimes():
    got = rpc("resources/list")["result"]
    assert got["resultType"] == "complete" and got["cacheScope"] == "public" and got["ttlMs"] == 300_000
    assert [r["uri"] for r in got["resources"]] == ["knos://fees", "knos://cheats"]
    tpl = rpc("resources/templates/list")["result"]["resourceTemplates"]
    assert [t["uriTemplate"] for t in tpl] == ["knos://bounty/{owner}/{repo}/{issue}", "knos://due/{login}", "knos://token/{address}"]
    assert all(t["mimeType"] == "application/json" and t["description"] for t in tpl)


def test_the_fees_and_the_cheat_rules_read_as_json():
    fees = rpc("resources/read", {"uri": "knos://fees"})["result"]
    (c,) = fees["contents"]
    assert c["uri"] == "knos://fees" and c["mimeType"] == "application/json" and fees["ttlMs"] == 30_000
    body = json.loads(c["text"])
    assert body["fees"]["x402_check"]["usd_each"] == "0.02" and body["revenue_today"] == "0"
    rules = json.loads(rpc("resources/read", {"uri": "knos://cheats"})["result"]["contents"][0]["text"])["rules"]
    ids = {r["id"] for r in rules}
    assert "gate.test_edited" in ids and any(r["category"] == "workflow_edited" for r in rules)


def test_a_bounty_and_an_account_read_through_the_same_code_as_their_tools():
    ledger, github = world()
    got = json.loads(rpc("resources/read", {"uri": "knos://bounty/octo/widgets/7"}, ledger, github)["result"]["contents"][0]["text"])
    (tool,) = talk([{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "knos_bounty", "arguments": {"issue": "octo/widgets#7"}, **META}}],
                   ledger, github)
    assert got == json.loads(json.dumps(tool["result"]["structuredContent"], default=str))
    due = json.loads(rpc("resources/read", {"uri": "knos://due/mona"}, ledger, github)["result"]["contents"][0]["text"])
    assert due["login"] == "mona"


def test_a_token_reads_its_safety_from_the_chain():
    from test_platform_token22 import PK, mint, tlv

    from knos.settle.v2 import pay

    class L:
        def infos(self, keys):
            return [(pay.TOKEN_2022, mint(tlv(12, PK)))]
    s = mcp.Server(ledger=L(), github=lambda p: {})
    addr = str(Pubkey.from_bytes(PK))
    got = json.loads(s.answer({"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": f"knos://token/{addr}"}})["result"]["contents"][0]["text"])
    assert got["kind"] == "mint" and got["ok"] is False and got["risks"][0]["extension"] == "PermanentDelegate"


@pytest.mark.parametrize("uri", ["knos://nothing", "knos://bounty/../x/1", "file:///etc/passwd", "knos://token/not-base58!", None])
def test_an_unknown_uri_is_a_not_found_error(uri):
    err = rpc("resources/read", {"uri": uri})["error"]
    assert err["code"] == -32602


def test_knos_mcp_repos_holds_resources_to_its_list(monkeypatch):
    monkeypatch.setenv("KNOS_MCP_REPOS", "octo/gadgets")
    ledger, github = world()
    err = rpc("resources/read", {"uri": "knos://bounty/octo/widgets/7"}, ledger, github)["error"]
    assert err["code"] == -32602 and "KNOS_MCP_REPOS" in err["message"]


def test_prompts_are_listed_and_filled_in():
    listed = rpc("prompts/list")["result"]["prompts"]
    assert [p["name"] for p in listed] == ["earn_a_bounty", "fund_a_bounty", "before_pull_request"]
    got = rpc("prompts/get", {"name": "fund_a_bounty", "arguments": {"issue": "octo/widgets#7", "amount": "20"}})["result"]
    (m,) = got["messages"]
    assert m["role"] == "user" and "octo/widgets#7" in m["content"]["text"] and "Post nothing until I say yes" in m["content"]["text"]
    assert "knos://cheats" in rpc("prompts/get", {"name": "earn_a_bounty"})["result"]["messages"][0]["content"]["text"]
    assert rpc("prompts/get", {"name": "fund_a_bounty", "arguments": {"issue": "o/r#1"}})["error"]["code"] == -32602
    assert rpc("prompts/get", {"name": "nope"})["error"]["code"] == -32602


def test_every_tool_declares_an_object_output_and_returns_one():
    ledger, github = world()
    listed = rpc("tools/list")["result"]["tools"]
    assert all(t["outputSchema"] == {"type": "object"} for t in listed)
    (r,) = talk([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "knos_due", "arguments": {"login": "mona"}, **META}}], ledger, github)
    assert isinstance(r["result"]["structuredContent"], dict)


# ---- a person confirms each post -----------------------------------------------------------------------------------------

def call(params: dict, ledger, github, hub) -> dict:
    stdin = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}) + "\n")
    out = io.StringIO()
    server = mcp.Server(ledger, github, post=hub.post, bind=hub.bind, scopes=lambda tok: None)
    for line in stdin:
        out.write(json.dumps(server.line(line)) + "\n")
    return json.loads(out.getvalue())["result"]


TAKE = {"name": "knos_take_work", "arguments": {"issue": f"octo/widgets#{ISSUE}"}}


def test_a_client_that_can_ask_the_person_gets_the_exact_post_to_approve_first(acting):  # noqa: F811
    ledger, github, hub = agent_world()
    first = call({**TAKE, **ELICIT}, ledger, github, hub)
    assert first["resultType"] == "input_required" and hub.sent == []                       # nothing posted yet
    ask = first["inputRequests"]["confirm"]
    assert ask["method"] == "elicitation/create" and ask["params"]["mode"] == "form"
    assert f"POST /repos/octo/widgets/issues/{ISSUE}/comments" in ask["params"]["message"] and "/knos take" in ask["params"]["message"]
    assert ask["params"]["requestedSchema"]["required"] == ["post"]
    yes = call({**TAKE, **ELICIT, "requestState": first["requestState"],
                "inputResponses": {"confirm": {"action": "accept", "content": {"post": True}}}}, ledger, github, hub)
    assert yes["resultType"] == "complete" and yes["isError"] is False and yes["structuredContent"]["sent"] is True
    assert hub.sent == [{"method": "POST", "path": f"repos/octo/widgets/issues/{ISSUE}/comments", "body": {"body": "/knos take"}}]


def test_a_no_or_a_forged_state_sends_nothing(acting):  # noqa: F811
    ledger, github, hub = agent_world()
    first = call({**TAKE, **ELICIT}, ledger, github, hub)
    no = call({**TAKE, **ELICIT, "requestState": first["requestState"], "inputResponses": {"confirm": {"action": "decline"}}}, ledger, github, hub)
    assert no["isError"] is True and "did not approve" in no["content"][0]["text"] and hub.sent == []
    unticked = call({**TAKE, **ELICIT, "requestState": first["requestState"],
                     "inputResponses": {"confirm": {"action": "accept", "content": {"post": False}}}}, ledger, github, hub)
    assert unticked["isError"] is True and hub.sent == []
    import base64
    st = json.loads(base64.urlsafe_b64decode(first["requestState"]))
    st["approved"] = [st["pending"]]                                             # a client that says it was approved
    forged = base64.urlsafe_b64encode(json.dumps(st).encode()).decode()
    again = call({**TAKE, **ELICIT, "requestState": forged}, ledger, github, hub)
    assert again["resultType"] == "input_required" and hub.sent == []           # the seal is over the digest and is still checked...
    st["seals"] = {st["pending"]: "0" * 64}
    worse = call({**TAKE, **ELICIT, "requestState": base64.urlsafe_b64encode(json.dumps(st).encode()).decode(),
                  "inputResponses": {"confirm": {"action": "accept", "content": {"post": True}}}}, ledger, github, hub)
    assert worse["resultType"] == "input_required" and hub.sent == []           # ...and a seal it did not make approves nothing
    other = call({"name": "knos_submit_work", "arguments": {"issue": f"octo/widgets#{ISSUE}", "path": ".", "branch": "b", "title": "t"},
                  **ELICIT, "requestState": first["requestState"], "inputResponses": {"confirm": {"action": "accept", "content": {"post": True}}}},
                 ledger, github, hub)
    assert other.get("resultType") != "complete" or other["isError"] or hub.sent == []


def test_an_unattended_agent_or_an_older_client_is_not_asked(acting, monkeypatch):  # noqa: F811
    ledger, github, hub = agent_world()
    assert call({**TAKE, **META}, ledger, github, hub)["structuredContent"]["sent"] is True       # no elicitation capability
    ledger, github, hub = agent_world()
    monkeypatch.setenv("KNOS_AGENT_CONFIRM", "0")
    assert call({**TAKE, **ELICIT}, ledger, github, hub)["structuredContent"]["sent"] is True
