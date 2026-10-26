"""test_dev_loop_speed: one champion run (champion.yml) passes its 8 tests in at most half the wall time of the
baseline run 39882739899 (12.3 min, so 6.15 min), with the same limits. Reads GitHub's record of the run.

    python scripts/test_dev_loop_speed.py [run id]        (default: the latest champion run)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = "drexthealpha/Knos"
EIGHT = ("test_fields_matrix", "test_value_vectors", "test_proof_first", "test_money_page", "test_companies_mode", "test_legibility",
         "test_vitals", "test_stack_coverage")
TARGET_MIN = 12.3 / 2
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")


def gh(*args: str) -> dict | list:
    return json.loads(subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout)


def t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(argv: list[str]) -> int:
    run = argv[0] if argv else str(gh("run", "list", "-R", REPO, "-w", "champion.yml", "-L", "1", "--json", "databaseId")[0]["databaseId"])
    v = gh("run", "view", run, "-R", REPO, "--json", "createdAt,updatedAt,jobs,headSha")
    jobs = {j["name"]: j for j in v["jobs"]}
    wall = (t(v["updatedAt"]) - t(v["createdAt"])).total_seconds() / 60
    lines = [f"run {run} at {v['headSha'][:8]}: {v['createdAt']} -> {v['updatedAt']}, {wall:.2f} min (target {TARGET_MIN:.2f})"]
    lines += [f"  {j['name']}: {j['conclusion']} {j['startedAt'][11:19]}-{(j.get('completedAt') or '')[11:19]}" for j in v["jobs"]]
    passed = [n for n in EIGHT if (jobs.get(n) or {}).get("conclusion") == "success"]
    ok = len(passed) == 8 and wall <= TARGET_MIN
    lines.append(("PASS" if ok else "FAIL") + f" test_dev_loop_speed: {len(passed)} of 8 tests, {wall:.2f} min of {TARGET_MIN:.2f}"
                 + ("" if ok else f"; failed: {[n for n in EIGHT if n not in passed]}"))
    print("\n".join(lines))
    (WORLD / "test_dev_loop_speed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
