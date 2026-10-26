"""test_stack_coverage, live: the Qloo coverage file (docs/reference/QLOO-COVERAGE.md) is what its generator writes
from the official docs read on the date it carries, and no capability is marked USED without a place a person reaches
it: every USED row names where a person meets it, and the live app answers.

    python scripts/test_stack_coverage.py [https://knos.onrender.com]
"""
from __future__ import annotations

import importlib.util
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


for name in ("qloo_coverage",):
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{name}.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    ok(run.returncode == 0, f"{name}: the file is what the docs and the code say", run.stdout.strip()[-80:])
    ok(READ in (ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8"), f"{name}: the official docs read on {READ}")

q = load("qloo_coverage")
qused = [r for r in q.insights_rows() + q.endpoint_rows() if r[2] == "USED"]
ok(all(("app " in r[3] or "/mcp" in r[3] or "front door" in r[3] or "API" in r[3] or "check.py" in r[3]) for r in qused),
   f"qloo_coverage: {len(qused)} USED, each naming where a person meets it")
ok(answers("/openapi.json") == 200, f"{BASE}/openapi.json answers")
print("PASS test_stack_coverage" if not fails else f"FAIL test_stack_coverage ({len(fails)})")
sys.exit(1 if fails else 0)
