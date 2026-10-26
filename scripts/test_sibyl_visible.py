"""test_sibyl_visible, live: the hosted MCP's knos_memory_search answers with Sibyl's verdict object and its code; a
real funding receipt from the app (a milestone funded from the app's devnet test wallet by the operator) carries what
Sibyl kept of its record line, and the app's own receipt drawing shows "Remembered by Sibyl: <tier>, verdict <code>".
The unit tests (apps/wanted/tests/test_sibyl_visible.py) hold the rest: both writes, and no call to Sibyl's paid learn().

    KNOS_ADMIN_KEY=... python scripts/test_sibyl_visible.py <commit sha under test>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_sibyl_visible.txt"
APP = "https://knos.onrender.com"
BRIEF = "autoresearch"


def http(path: str, body: dict | None = None, headers: dict | None = None, timeout: float = 600) -> tuple[int, dict]:
    req = urllib.request.Request(APP + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "knos-test-sibyl-visible", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main(sha: str) -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    dep = subprocess.run([sys.executable, "-I", os.environ["KNOS_RENDER_LATEST"]], capture_output=True, text=True).stdout.strip() if os.environ.get("KNOS_RENDER_LATEST") else ""
    first = dep.splitlines()[0] if dep else ""
    ok(first.endswith(sha[:8]) and " live " in first, f"Render's newest deploy: {first or 'not read'} (the commit under test {sha[:8]})")
    st, got = http("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "knos_memory_search", "arguments": {"q": "funded"}}})
    sc = ((got.get("result") or {}).get("structuredContent")) or {}
    ok(st == 200 and isinstance(sc.get("verdict"), dict) and sc.get("verdict_code") == sc["verdict"].get("code"),
       f"knos_memory_search: Sibyl's verdict object {json.dumps(sc.get('verdict'))[:200]}, code {sc.get('verdict_code')!r}")
    admin = {"X-Knos-Admin": os.environ["KNOS_ADMIN_KEY"]}
    pid = next((p["id"] for p in http("/api/projects?take=100")[1].get("projects", []) if p.get("solver_brief") == BRIEF), None)
    if pid is None:
        opened = http("/api/project/operator", {"action": "solver_open", "which": [BRIEF]}, admin)[1]
        pid = ((opened.get("projects") or [{}])[0]).get("id")
    st, fund = http("/api/project/operator", {"action": "solver_fund", "project": pid, "units": 5}, admin)
    s = fund.get("sibyl") or {}
    ok(st == 200 and fund.get("status") == "locked" and s.get("tier") and s.get("verdict"),
       f"a real funding receipt (order {str(fund.get('order'))[:12]}..., lock {str((fund.get('signatures') or {}).get('lock'))[:12]}...): sibyl {s}")
    shown = ""
    if s:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            try:
                page = b.new_page()
                page.goto(APP + "/paid", wait_until="load")
                page.wait_for_function("typeof receipt === 'function'", timeout=60000)
                shown = page.evaluate("(p) => { receipt(p); return document.querySelector('#receipt [data-sibyl]')?.textContent || ''; }", fund)
            finally:
                b.close()
    want = f"Remembered by Sibyl: {s.get('tier')}, verdict {s.get('verdict')}"
    ok(shown == want, f"the app's receipt shows {shown!r}")
    lines.append(f"FAIL test_sibyl_visible: {fails} check(s) failed" if fails else
                 f"PASS test_sibyl_visible: knos_memory_search hands on Sibyl's verdict ({sc.get('verdict_code')}); a live receipt shows \"{shown}\"")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
