"""test_stack_coverage, live: the three coverage files (Solana devnet, Sibyl's free plan, Qloo's hackathon API) are what
their generators write from the official docs read on the date they carry, and no capability is marked USED without a
place a person reaches it: every USED row names at least one interface, and every API route a row names answers on the
live app (not 404).

    python scripts/test_stack_coverage.py [https://knos.onrender.com]
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://knos.onrender.com"
READ = "22 Oct 2026"
fails = []


def ok(cond: bool, what: str, extra=None) -> None:
    print(("ok   " if cond else "FAIL ") + what + (f" {extra}" if extra is not None else ""))
    if not cond:
        fails.append(what)


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def answers(path: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"User-Agent": "knos test_stack_coverage"}), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


for name in ("solana_coverage", "sibyl_coverage", "qloo_coverage"):
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{name}.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    ok(run.returncode == 0, f"{name}: the file is what the docs and the code say", run.stdout.strip()[-80:])
    ok(READ in (ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8"), f"{name}: the official docs read on {READ}")

P = ("app", "front", "mcp", "api", "cli")
routes = set()
for name in ("solana_coverage", "sibyl_coverage"):
    m = load(name)
    rows = list(m.ROWS) + (m.rpc_rows() if hasattr(m, "rpc_rows") else [])
    used = [r for r in rows if r["status"] == "USED"]
    nowhere = [r["cap"] for r in used if all((r.get(k) or "—") == "—" for k in P)]
    ok(not nowhere, f"{name}: {len(used)} USED, each with a place a person reaches it", nowhere[:5] or None)
    for r in used:
        routes |= set(re.findall(r"`GET (/api/[a-z0-9/_-]+)", r.get("api") or ""))
q = load("qloo_coverage")
qused = [r for r in q.insights_rows() + q.endpoint_rows() if r[2] == "USED"]
ok(all(("app " in r[3] or "/mcp" in r[3] or "front door" in r[3] or "API" in r[3] or "check.py" in r[3]) for r in qused),
   f"qloo_coverage: {len(qused)} USED, each naming where a person meets it")
# a route that needs an id answers 404 for none: the live app's own OpenAPI document says which routes it serves
import json  # noqa: E402

served = set(json.loads(urllib.request.urlopen(BASE + "/openapi.json", timeout=60).read())["paths"])
dead = sorted(p for p in routes if p not in served and answers(p) == 404)
ok(not dead, f"{len(routes)} API routes the rows name are served by {BASE} (its /openapi.json, or a live answer)", dead or None)
print("PASS test_stack_coverage" if not fails else f"FAIL test_stack_coverage ({len(fails)})")
sys.exit(1 if fails else 0)
