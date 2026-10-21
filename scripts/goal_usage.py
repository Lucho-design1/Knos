"""One Claude Code goal's own token use, read from its session transcript (TASK-QLOO-CHAMPION M11).

    python scripts/goal_usage.py <session .jsonl> --since 2026-10-21T15:13:34Z [--goal TASK-QLOO-CHAMPION] [--out docs/idt/self_usage.json]

Sums the `usage` the API returned on every assistant message after `--since` (each message counted once, by its id):
output tokens (thinking included), input tokens, and cache reads and writes. The same numbers are recorded on the
hosted server through the knos_usage MCP tool (scripts/goal_usage.py --record), and the home page shows them beside
the 2.08x IDT ratio, which is the IDT benchmark's own result, not this goal's. Nothing is estimated.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def usage(path: Path, since: str) -> dict:
    """Per message id the largest usage the transcript holds for it (a message can be written in several lines)."""
    keys = ("output_tokens", "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    per: dict[str, dict] = {}
    last = since
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "assistant" or (d.get("timestamp") or "") < since:
                continue
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            row = per.setdefault(m.get("id") or d.get("uuid"), dict.fromkeys(keys, 0))
            for k in keys:
                row[k] = max(row[k], int(u.get(k) or 0))
            last = max(last, d.get("timestamp") or last)
    tot = {k: sum(r[k] for r in per.values()) for k in keys}
    return {**tot, "messages": len(per), "since": since, "until": last}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--since", required=True)
    ap.add_argument("--goal", default="TASK-QLOO-CHAMPION")
    ap.add_argument("--out", default=str(ROOT / "docs" / "idt" / "self_usage.json"))
    ap.add_argument("--record", action="store_true", help="also record it on the hosted server (knos_usage, the operator's key)")
    a = ap.parse_args(argv)
    u = {"v": 1, "goal": a.goal, "measured_with": "the Claude Code session transcript: usage as the API returned it, each message once",
         **usage(Path(a.transcript), a.since)}
    Path(a.out).write_text(json.dumps(u, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(u))
    if a.record:
        base = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com")
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "knos_usage", "arguments": {"record": u}}}
        req = urllib.request.Request(base + "/mcp", json.dumps(body).encode(), {"Content-Type": "application/json",
                                     "X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            print("knos_usage:", json.loads(r.read())["result"]["content"][0]["text"][:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
