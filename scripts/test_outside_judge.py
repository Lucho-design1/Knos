"""TASK-CHAMPION T10 test_outside_judge: the latest outside review of the live site, by a fresh agent with no context,
scored every rule and judge 100 of 100, or named the gap only real outside people can close with its live count.

    python scripts/test_outside_judge.py [scripts/outside_judge.json]

The summary is what the operator recorded from that review: its date, how many scores, how many at 100, the gaps
outside people close, and the sha256 of the full report (kept private: it names people). It passes when every score
not held by an outside-only gap is 100 and the review is at most 7 days old.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    s = json.loads(Path(argv[0] if argv else HERE / "outside_judge.json").read_text(encoding="utf-8"))
    fails = 0

    def ok(c: bool, msg: str) -> None:
        nonlocal fails
        print(("ok   " if c else "FAIL ") + msg)
        fails += 0 if c else 1

    age = (date.today() - datetime.strptime(s["date"], "%Y-%m-%d").date()).days
    ok(age <= 7, f"review of {s['date']} ({age} days old), by {s['by']}; full report sha256 {s['report_sha256'][:16]}")
    held = {g["score"] for g in s["outside_gaps"]}
    below = [x for x in s["scores"] if x["score"] < 100 and x["name"] not in held]
    ok(not below, f"{len(s['scores'])} scores: {sum(x['score'] == 100 for x in s['scores'])} at 100"
       + ("; below 100: " + ", ".join(f"{x['name']} {x['score']}" for x in below) if below else ""))
    for g in s["outside_gaps"]:
        print(f"     outside only: {g['score']}: {g['gap']} (live count {g['live_count']})")
    print("FAIL test_outside_judge" if fails else "PASS test_outside_judge")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
