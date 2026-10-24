"""test_ci_green: the full tests.yml run on a commit (default: main's head) has 0 failed jobs and 0 failed tests, the
front door's 320 px test and the statement's PDF reader test included. Reads GitHub's record of the run.

    python scripts/test_ci_green.py [commit sha]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = "drexthealpha/Knos"
WORLD = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world"))


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def main(argv: list[str]) -> int:
    sha = argv[0] if argv else json.loads(gh("api", f"repos/{REPO}/commits/main"))["sha"]
    runs = json.loads(gh("run", "list", "-R", REPO, "-w", "tests.yml", "-c", sha, "--json", "databaseId,status,conclusion"))
    if not runs or runs[0]["status"] != "completed":
        line = f"FAIL test_ci_green: no completed tests.yml run on {sha[:8]} yet"
    else:
        rid = str(runs[0]["databaseId"])
        jobs = json.loads(gh("run", "view", rid, "-R", REPO, "--json", "jobs"))["jobs"]
        bad = [j for j in jobs if j["conclusion"] not in ("success", "skipped")]
        failed = set()
        for j in bad:
            log = subprocess.run(["gh", "api", f"repos/{REPO}/actions/jobs/{j['databaseId']}/logs"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace").stdout or ""
            failed |= set(re.findall(r"FAILED (\S+)", log))
        line = (f"PASS test_ci_green: run {rid} on {sha[:8]}, {len(jobs)} jobs, 0 failed" if not bad else
                f"FAIL test_ci_green: run {rid} on {sha[:8]}: {len(bad)} job(s) failed, tests {sorted(failed)[:5]}")
    print(line)
    (WORLD / "test_ci_green.txt").write_text(line + "\n", encoding="utf-8")
    return 0 if line.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
