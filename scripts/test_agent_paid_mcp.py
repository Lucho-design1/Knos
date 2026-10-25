"""test_agent_paid_mcp: an agent with a capped key is paid through the hosted MCP, from the founder's own Claude Code.

Step 0, with scripts/test_agent_solver.py's own functions: one funded open milestone on devnet (the operator's key
from KNOS_ADMIN_KEY) and one capped agent key for it, paid at a fresh address. The key goes to
<world>/e3-<timestamp>/agent.key (one line) and is never printed. Step 1: .mcp.json in that folder, exactly as the
front door shows it, with ${KNOS_AGENT_KEY}. Step 2: KNOS_AGENT_KEY in claude's environment only (never on a command
line), then claude -p with --strict-mcp-config --mcp-config .mcp.json and only the knos MCP tools allowed. Pass: the
demand check returned a verdict, a SIG: line is present, and that transaction is confirmed on devnet and pays the
agent's address. The key is revoked and the folder deleted afterwards.

    KNOS_ADMIN_KEY=... python scripts/test_agent_paid_mcp.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world"))
OUT = WORLD / "test_agent_paid_mcp.txt"
MCP_JSON = '{"mcpServers":{"knos":{"type":"http","url":"https://knos.onrender.com/mcp","headers":{"Authorization":"Bearer ${KNOS_AGENT_KEY}"}}}}'
PROMPT = ("Use the knos tools only. Run a demand check for 'a smart water bottle that glows to remind you to drink'. Then find the "
          "open funded milestone you are allowed to work on, complete it, and report the payout transaction signature on one line "
          "starting with SIG:.")


def solver():
    spec = importlib.util.spec_from_file_location("test_agent_solver", HERE / "test_agent_solver.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tx(rpc: str, sig: str) -> dict | None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                       "params": [sig, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}]}).encode()
    with urllib.request.urlopen(urllib.request.Request(rpc, body, {"Content-Type": "application/json"}), timeout=60) as r:
        return json.loads(r.read()).get("result")


def main() -> int:
    s = solver()
    lines: list[str] = []
    if not os.environ.get("KNOS_ADMIN_KEY"):
        lines.append("FAIL test_agent_paid_mcp: BLOCKED: KNOS_ADMIN_KEY (the operator's key) is not in the environment")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1
    from solders.keypair import Keypair
    payout = str(Keypair().pubkey())                       # the key pair is dropped: only the address is kept
    target = s.funded_project()
    folder = WORLD / f"e3-{time.strftime('%Y%m%d%H%M%S')}"
    owner = kid = None
    ok = False
    try:
        if target is None:
            lines.append("FAIL step 0: no funded open milestone")
            raise SystemExit
        pid, mkey = target
        lines.append(f"step 0: funded open milestone {pid}/{mkey}")
        owner = s.http("/api/auth/guest", {"label": "e3 test owner"})[1].get("token")
        st, made = s.http("/api/agent/keys", {"label": "e3 agent", "max_claims": 1, "max_spend_units": 10, "days": 1, "payout_wallet": payout}, owner)
        key = str(made.get("key", ""))
        if st != 200 or not key.startswith("knos_ak_"):
            lines.append(f"FAIL step 0: no agent key ({st})")
            raise SystemExit
        kid = made["id"]
        lines.append(f"step 0: capped agent key {kid} (max 1 claim, 10 units, 1 day), paid at a fresh address")
        folder.mkdir()
        (folder / "agent.key").write_text(key + "\n", encoding="utf-8")
        (folder / ".mcp.json").write_text(MCP_JSON, encoding="utf-8")
        before = s.balance(payout)
        exe = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
        env = {**os.environ, "KNOS_AGENT_KEY": (folder / "agent.key").read_text(encoding="utf-8").strip()}
        env.pop("KNOS_ADMIN_KEY", None)                    # the agent's process never holds the operator's key
        run = subprocess.run([exe, "-p", PROMPT, "--strict-mcp-config", "--mcp-config", ".mcp.json", "--allowedTools", "mcp__knos__*",
                              "--output-format", "stream-json", "--verbose"], cwd=folder, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=2400)
        calls, results, final = [], {}, ""
        for raw in run.stdout.splitlines():
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    calls.append((c["id"], c["name"]))
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    results[c.get("tool_use_id")] = json.dumps(c.get("content"))
            if ev.get("type") == "result":
                final = str(ev.get("result") or "")
        for cid, name in calls:
            lines.append(f"  tool {name}: {results.get(cid, 'no result')[:160].replace(key, '<key>')}")
        verdict = any(n.endswith("knos_demand_check") and '\\"verdict\\"' in results.get(i, "") for i, n in calls)
        m = re.search(r"^\s*SIG:\s*([1-9A-HJ-NP-Za-km-z]{80,90})\s*$", final, re.M)
        sig = m[1] if m else None
        lines.append(f"claude -p exit {run.returncode}; demand check verdict {'returned' if verdict else 'missing'}; SIG {'line present' if sig else 'missing'}")
        paid = False
        if sig:
            t = tx(s.RPC, sig)
            meta = (t or {}).get("meta") or {}

            def held(rows):
                return sum(float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0) for b in rows or [] if b.get("owner") == payout)
            gain = held(meta.get("postTokenBalances")) - held(meta.get("preTokenBalances"))
            paid = bool(t) and meta.get("err") is None and gain > 0
            lines.append(f"devnet: transaction {sig[:10]}... {'confirmed' if t else 'not found'}, the agent's address gained {gain:g} test units")
        after = s.balance(payout)
        lines.append(f"the agent's address holds {after:g} test units (was {before:g})")
        ok = verdict and bool(sig) and paid
    except SystemExit:
        pass
    finally:
        if owner and kid:
            s.http("/api/agent/keys/revoke", {"id": kid}, owner)
            lines.append(f"agent key {kid} revoked")
        shutil.rmtree(folder, ignore_errors=True)
        lines.append(f"folder deleted: {not folder.exists()}")
    lines.append("PASS test_agent_paid_mcp: demand check verdict, SIG line, payout confirmed on devnet to the agent's address, 0 manual steps"
                 if ok else "FAIL test_agent_paid_mcp: " + ("no verdict from the demand check; " if not any("verdict returned" in x for x in lines) else "")
                 + ("no confirmed payout to the agent's address" if not ok else ""))
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
