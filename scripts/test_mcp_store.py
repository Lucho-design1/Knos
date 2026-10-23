"""TASK-WORLD T5 test_mcp_store_ready, live: the hosted MCP is ready for the AI app stores.

    python scripts/test_mcp_store.py [https://knos.onrender.com]

Claude's connector directory: an https URL, every tool with a title and readOnlyHint or destructiveHint, read-only tools
usable with no sign-in, a privacy policy URL and a docs URL that answer. ChatGPT's app rules: no money moves inside the
assistant, so the app-store profile (/mcp/store) lists only knos_ready, knos_demand_check and the qloo_* tools, and
refuses every other tool. Both profiles are rate-limited per address, and the store profile has a daily call cap.
The rate limit is probed last (cheap pings), since it holds this address back for a few minutes.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

APP = (sys.argv[1] if len(sys.argv) > 1 else "https://knos.onrender.com").rstrip("/")
PRIVACY = "https://drexthealpha.github.io/Knos/privacy.html"
DOCS = "https://github.com/drexthealpha/Knos/blob/main/docs/reference/MCP_STORE.md"
fails = 0


def ok(c: bool, msg: str) -> None:
    global fails
    print(("ok   " if c else "FAIL ") + msg)
    fails += 0 if c else 1


def rpc(path: str, method: str, params: dict | None = None, i: int = 1) -> tuple[int, dict]:
    req = urllib.request.Request(APP + path, json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}).encode(),
                                 {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": "knos-store-check"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "knos-store-check"}), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


s, init = rpc("/mcp/store", "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "store-check", "version": "1"}})
ok(s == 200 and APP.startswith("https://") and init.get("result", {}).get("serverInfo"), f"https endpoint {APP}/mcp/store answers initialize")
_, full = rpc("/mcp", "tools/list")
tools = full.get("result", {}).get("tools", [])
bad = [t["name"] for t in tools if not ((t.get("annotations") or {}).get("title") and isinstance((t.get("annotations") or {}).get("readOnlyHint"), bool)
                                         and isinstance((t.get("annotations") or {}).get("destructiveHint"), bool))]
ok(tools and not bad, f"every one of {len(tools)} tools on /mcp has a title, readOnlyHint and destructiveHint" + (f" (missing: {bad})" if bad else ""))
money = [t["name"] for t in tools if (t.get("annotations") or {}).get("destructiveHint")]
ok("knos_preorder" in money, f"the money tool is marked destructive: {money}")
_, st = rpc("/mcp/store", "tools/list")
store = [t["name"] for t in st.get("result", {}).get("tools", [])]
allowed = all(n in ("knos_ready", "knos_demand_check") or n.startswith("qloo_") for n in store)
ok(allowed and "knos_ready" in store and "knos_demand_check" in store and not any(n == "knos_preorder" for n in store),
   f"the store profile lists only knos_ready, knos_demand_check and qloo_*: {store}")
ro = [t["name"] for t in st.get("result", {}).get("tools", []) if not (t.get("annotations") or {}).get("readOnlyHint")]
ok(not ro, "every tool in the store profile is read-only" + (f" (not: {ro})" if ro else ""))
_, refused = rpc("/mcp/store", "tools/call", {"name": "knos_preorder", "arguments": {}})
ok("error" in refused and "money moves on the Knos site" in json.dumps(refused), "a money tool is refused inside the assistant: " + json.dumps(refused.get("error"))[:120])
brief = {"milestones": [{"key": "m1", "name": "Pilot", "target": "100 units pass a 72 h soak test", "verifier": {"check": "test_soak"}, "deadline_days": 30}]}
_, r = rpc("/mcp/store", "tools/call", {"name": "knos_ready", "arguments": {"brief": brief}})
text = json.dumps(r.get("result") or {})
ok("Ready" in text and not r.get("error"), "knos_ready answers with no sign-in")
ok(status(PRIVACY) == 200, f"privacy policy {PRIVACY}")
ok(status(DOCS) == 200, f"docs {DOCS}")
codes = [rpc("/mcp/store", "ping", i=k)[0] for k in range(40)]
ok(429 in codes, f"rate-limited per address: {codes.count(200)} answered, then {codes.count(429)} refused with 429")
print("FAIL test_mcp_store_ready" if fails else "PASS test_mcp_store_ready")
sys.exit(1 if fails else 0)
