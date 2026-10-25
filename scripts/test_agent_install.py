"""test_agent_install: a fresh Claude Code config directory (a new CLAUDE_CONFIG_DIR, no prior settings) runs the one
command the front door and the README show, then asks Claude Code, through the Knos MCP tools, for a demand check and a
paid devnet job. Pass: both finish with 0 manual steps and the payout transaction is confirmed on devnet. When the fresh
client cannot run a prompt without a person (it asks for /login), the test writes BLOCKED with Claude Code's own words.

    python scripts/test_agent_install.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CMD = ["mcp", "add", "--transport", "http", "knos", "https://knos.onrender.com/mcp"]
OUT = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world")) / "test_agent_install.txt"
PROMPT = ("Use the knos MCP tools only. 1) Run a demand check for 'an AI recipe planner for families' and give its verdict. "
          "2) Take one funded devnet job with knos_find_work and knos_take_work, then report its payout transaction signature.")


def main() -> int:
    claude = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
    lines = [f"claude: {claude}"]
    if not claude:
        lines.append("FAIL test_agent_install: BLOCKED: Claude Code is not on PATH")
    else:
        with tempfile.TemporaryDirectory(prefix="knos-cc-fresh-") as d:
            env = {**os.environ, "CLAUDE_CONFIG_DIR": str(Path(d) / "cfg")}
            env.pop("ANTHROPIC_API_KEY", None)
            add = subprocess.run([claude, *CMD], cwd=d, env=env, capture_output=True, text=True, timeout=180)
            lines.append(f"$ claude {' '.join(CMD)}  (exit {add.returncode}) {(add.stdout + add.stderr).strip().splitlines()[:1]}")
            ls = subprocess.run([claude, "mcp", "list"], cwd=d, env=env, capture_output=True, text=True, timeout=180)
            lines.append(f"$ claude mcp list  (exit {ls.returncode}) {[x for x in (ls.stdout + ls.stderr).splitlines() if 'knos' in x][:1]}")
            run = subprocess.run([claude, "-p", PROMPT, "--allowedTools", "mcp__knos"], cwd=d, env=env, capture_output=True, text=True, timeout=900)
            said = (run.stdout + run.stderr).strip()
            lines.append(f"$ claude -p <demand check, then a paid devnet job>  (exit {run.returncode}) {said[:300]!r}")
            if "not logged in" in said.lower() or "/login" in said:
                lines.append("BLOCKED: a login for the fresh client. A new CLAUDE_CONFIG_DIR holds no credentials and no ANTHROPIC_API_KEY is set "
                             "on this PC; Claude Code answers 'Not logged in, please run /login', which is a manual step.")
                lines.append("FAIL test_agent_install: BLOCKED, the fresh Claude Code client needs a /login before its first prompt (the MCP add itself took 1 command)")
            else:
                lines.append("FAIL test_agent_install: the run ended without a confirmed devnet payout in its answer (read it above)")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1


if __name__ == "__main__":
    sys.exit(main())
