"""The Node sidecar with the OFFICIAL MCP SDK, against a fake MCP server (Knos's MOCK server as a separate process):
the exact path live mode takes to `qloo mcp`, with no network and no key. Needs Node and the SDK installed beside the
bridge (sh apps/wanted/bridge/install.sh); skipped, with that reason, where they are not."""
import pytest

from knos_wanted import qloo_mcp
from knos_wanted.qloo_mcp import Bridge, Qloo

why_not = Bridge.available()
pytestmark = pytest.mark.skipif(why_not is not None, reason=why_not or "")


def test_bridge_talks_mcp_to_a_fake_server():
    c = Qloo(Bridge(mock=True), sleep=lambda s: None)
    try:
        assert c.mode == "mock" and c.server["name"] == "knos-qloo-mock" and len(c.tools) == 10
        trail = []
        env = c.call("qloo_describe", {"entity": "Starbucks", "type": "place"}, why="t", trail=trail)
        assert env["status"] == "needs_input" and qloo_mcp.candidates(env)
        cid = qloo_mcp.candidates(env)[0]["id"]
        env = c.call("qloo_where_popular", {"entity": cid, "within": "London", "limit": 3}, why="t", trail=trail)
        assert env["status"] == "ok" and env["result_count"] == 3 and env["_mock"] == qloo_mcp.MOCK_LABEL
    finally:
        c.close()


def test_bridge_retries_through_the_real_transport():
    c = Qloo(Bridge(mock=True, extra_env={"KNOS_WANTED_MOCK_FAIL": "qloo_find_tags:QLOO_UPSTREAM:retryable:1"}), sleep=lambda s: None)
    try:
        trail = []
        env = c.call("qloo_find_tags", {"query": "jazz"}, why="t", trail=trail)
        assert env["status"] == "ok" and trail[0]["attempts"] == 2
    finally:
        c.close()


def test_missing_server_command_is_a_clear_error():
    b = Bridge(extra_env={"QLOO_MCP_COMMAND": "definitely-not-a-qloo-binary"})
    try:
        with pytest.raises(qloo_mcp.QlooUnavailable):
            b.init()
    finally:
        b.close()
