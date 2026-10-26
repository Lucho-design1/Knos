"""test_results_board, live: How we test Knos (Pages at the commit under test) has one table of every published outside
test, each once, with its 95% interval and a result that follows the interval only (above 0 a win, below 0 a loss,
holding 0 a tie); every link answers 200.

    python scripts/test_results_board.py <commit sha under test>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_results_board.txt"
PAGE = "https://drexthealpha.github.io/Knos/how-we-test.html"
# every outside test published (docs/reference/OUTSIDE_TRUTH.md), by the file of its result
PUBLISHED = ["where_truth.json", "taste_truth.json", "kickstarter_truth.json", "qloo_lift_ranked.json", "outside_truth.json"]


def status(u: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "knos-test"}), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def rule(interval: str) -> str:
    lo, hi = (float(x) for x in re.findall(r"[-+]?\d*\.\d+", interval)[:2])
    return "win" if lo > 0 else "loss" if hi < 0 else "tie"


def main(sha: str) -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    dep = json.loads(subprocess.run(["gh", "api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], capture_output=True, text=True, check=True).stdout)[0]
    ok(dep["sha"] == sha, f"Pages deployed at {dep['sha'][:7]} (commit under test {sha[:7]})")
    with urllib.request.urlopen(f"{PAGE}?t={int(time.time())}", timeout=60) as r:
        page = r.read().decode("utf-8")
    sec = re.search(r'<section class="t" id="board">(.*?)</section>', page, re.S)
    ok(bool(sec), "the table renders on the live page")
    rows = re.findall(r"<tr><td><a href=\"([^\"]+)\"[^>]*>(.*?)</a></td><td>.*?</td><td>.*?</td><td>.*?</td><td>(.*?)</td><td data-label=\"(\w+)\">", sec.group(1) if sec else "")
    files = [u.rsplit("/", 1)[-1] for u, *_ in rows]
    ok(sorted(files) == sorted(PUBLISHED) and len(files) == len(set(files)), f"every published test once: {len(rows)} rows {files}")
    for u, name, interval, label in rows:
        ok(rule(interval) == label, f"{name}: interval {interval} -> {label} (rule says {rule(interval)})")
    for u in sorted({u for u, *_ in rows}):
        ok(status(u) == 200, f"{status(u)} {u}")
    labels = [r[3] for r in rows]
    lines.append(f"FAIL test_results_board: {fails} check(s) failed" if fails else
                 f"PASS test_results_board: {len(rows)} tests, {labels.count('win')} win, {labels.count('tie')} tie, {labels.count('loss')} loss, every label by the rule, every link 200 (J4 not run)")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
