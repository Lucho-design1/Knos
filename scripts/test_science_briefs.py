"""TASK-WORLD T11 test_science_briefs, live: each research brief passes the hosted knos_ready (POST /mcp) unchanged, or
after the one rewrite knos_ready itself proposes; prints each brief's label and criteria hash.

    python scripts/test_science_briefs.py <briefs.json>        (a JSON list of briefs)
"""
from __future__ import annotations

import json
import sys
import urllib.request

MCP = "https://knos.onrender.com/mcp"


def ready(brief: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "knos_ready", "arguments": {"brief": brief}}}
    r = urllib.request.urlopen(urllib.request.Request(MCP, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=120)
    return json.loads(json.loads(r.read())["result"]["content"][0]["text"])


def main(argv: list[str]) -> int:
    briefs = json.loads(open(argv[0], encoding="utf-8").read())
    passed = 0
    for b in briefs:
        got, rewrites = ready(b), 0
        if not got["ready"]:                                  # one rewrite: knos_ready's own template for each milestone
            b = {**b, "milestones": [m.get("rewrite") or m["milestone"] for m in got["milestones"]]}
            got, rewrites = ready(b), 1
        passed += got["ready"]
        print(f"{'ok  ' if got['ready'] else 'FAIL'} {got['label']:9} rewrites {rewrites}  {b.get('title', '')[:60]}  "
              f"criteria {got.get('criteria_hash')}  {got['missing'][:3]}")
    print(("PASS" if passed == len(briefs) else "FAIL") + f" test_science_briefs: {passed} of {len(briefs)} Ready on the hosted knos_ready")
    return 0 if passed == len(briefs) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
