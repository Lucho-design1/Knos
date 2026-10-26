"""test_usage_trend: the usage counter's trend line, with stub data (apps/wanted/tests/test_usage_trend.py): the line
shows exactly for 12 this week and 5 the week before; nothing for (4, 1) or (12, 15); test sessions and automated
clients are left out of the days counted.

    python scripts/test_usage_trend.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world")) / "test_usage_trend.txt"


def main() -> int:
    run = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-v", "apps/wanted/tests/test_usage_trend.py"],
                         cwd=ROOT, capture_output=True, text=True, timeout=600)
    rows = [ln.split("::", 1)[1] for ln in run.stdout.splitlines() if "::" in ln and (" PASSED" in ln or " FAILED" in ln)]
    passed = sum(" PASSED" in r for r in rows)
    lines = [f"{'ok  ' if ' PASSED' in r else 'FAIL'} {r.split(' ')[0]}" for r in rows]
    ok = run.returncode == 0 and passed == 3
    lines.append(f"PASS test_usage_trend: the line shows exactly for (12, 5), nothing for (4, 1) and (12, 15), test sessions and automated clients left out ({passed} of 3 unit tests)"
                 if ok else f"FAIL test_usage_trend: {passed} of 3 unit tests passed")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
