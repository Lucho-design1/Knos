"""test_agent_install: the founder's own Claude Code (already signed in; no new config folder, no credential file read)
adds the hosted Knos MCP in a new empty folder with one command,

    claude mcp add --transport http --scope project knos https://knos.onrender.com/mcp

(which writes .mcp.json there), then runs claude -p with --strict-mcp-config --mcp-config .mcp.json and only the knos
MCP tools allowed, asking for a demand check and one paid devnet job. Pass: both tool calls succeed with 0 manual steps
and the transaction it reports is confirmed on devnet. The folder is deleted afterwards.

    python scripts/test_agent_install.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORLD = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world"))
OUT = WORLD / "test_agent_install.txt"
ADD = ["mcp", "add", "--transport", "http", "--scope", "project", "knos", "https://knos.onrender.com/mcp"]
PROMPT = ("Use the knos tools only. Run a demand check for 'a smart water bottle that glows to remind you to drink', then run "
          "one paid devnet job with the capped agent key and report the transaction signature.")
SIG = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{80,90}\b")


def confirmed(sig: str) -> dict | None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignatureStatuses", "params": [[sig], {"searchTransactionHistory": True}]}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://api.devnet.solana.com", body, {"Content-Type": "application/json"}), timeout=60) as r:
        return ((json.loads(r.read()).get("result") or {}).get("value") or [None])[0]


def main() -> int:
    claude = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
    folder = WORLD / f"d4-{time.strftime('%Y%m%d%H%M%S')}"
    folder.mkdir()
    lines = [f"folder {folder.name}"]
    try:
        add = subprocess.run([claude, *ADD], cwd=folder, capture_output=True, text=True, timeout=180)
        lines.append(f"$ claude {' '.join(ADD)}  (exit {add.returncode}) .mcp.json {'written' if (folder / '.mcp.json').exists() else 'missing'}")
        run = subprocess.run([claude, "-p", PROMPT, "--strict-mcp-config", "--mcp-config", ".mcp.json", "--allowedTools", "mcp__knos",
                              "--output-format", "stream-json", "--verbose"], cwd=folder, capture_output=True, text=True, timeout=1500)
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
                    text = json.dumps(c.get("content"))[:400]
                    results[c.get("tool_use_id")] = (bool(c.get("is_error")) or '"_error"' in text or "refused" in text.lower(), text)
            if ev.get("type") == "result":
                final = str(ev.get("result") or "")
        for cid, name in calls:
            err, text = results.get(cid, (True, "no result"))
            lines.append(f"  tool {name}: {'error' if err else 'ok'}  {text[:220]}")
        lines.append(f"$ claude -p ... (exit {run.returncode}) answer: {final[:600]!r}")
        if not calls:
            lines.append(f"  stream: {run.stdout[-600:]!r} {run.stderr[-300:]!r}")
        check_ok = any(n.endswith("knos_demand_check") and not results.get(i, (True,))[0] for i, n in calls)
        sigs = SIG.findall(final)
        st = confirmed(sigs[0]) if sigs else None
        paid = bool(st) and st.get("confirmationStatus") in ("confirmed", "finalized") and st.get("err") is None
        lines.append(f"demand check {'ok' if check_ok else 'not done'}; transaction {sigs[0][:10] + '... ' + str(st and st.get('confirmationStatus')) if sigs else 'none reported'}")
        ok = check_ok and paid
        lines.append(f"PASS test_agent_install: 1 command added the MCP; demand check and a paid devnet job ({sigs[0][:8]}... {st['confirmationStatus']}) with 0 manual steps"
                     if ok else f"FAIL test_agent_install: demand check {'done' if check_ok else 'not done'}, {'no confirmed payout transaction' if not paid else ''}".rstrip(", "))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        lines.append(f"folder deleted: {not folder.exists()}")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if lines[-2].startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
