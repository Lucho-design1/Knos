"""test_where_it_fails, live: How we test Knos (the Pages build at the commit under test) has its "Where it fails"
section with every result in it, each with its number, and every link of the section answers 200.

    python scripts/test_where_it_fails.py <commit sha under test>
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
OUT = WORLD / "test_where_it_fails.txt"
PAGE = "https://drexthealpha.github.io/Knos/how-we-test.html"
# each failure the section names, with the numbers it must state (docs/reference/OUTSIDE_TRUTH.md, where_truth.json)
RESULTS = {"the Census loss": ["0.193", "0.407"], "the film tie": ["0.320", "0.307", "[-0.060, +0.087]"],
           "the Kickstarter result": ["78.0%", "78.8%"], "ideas with no Qloo map": ["12 of 30"]}


def status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "knos-test"}), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main(sha: str) -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    dep = json.loads(subprocess.run(["gh", "api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"],
                                    capture_output=True, text=True, check=True).stdout)[0]
    ok(dep["sha"] == sha, f"Pages deployed at {dep['sha'][:7]} (the commit under test {sha[:7]})")
    with urllib.request.urlopen(f"{PAGE}?t={int(time.time())}", timeout=60) as r:
        page = r.read().decode("utf-8")
    m = re.search(r'<section class="t" id="where-it-fails">(.*?)</section>', page, re.S)
    ok(bool(m) and "<h2>Where it fails</h2>" in m.group(1), "the section renders on the live page")
    sec = m.group(1) if m else ""
    words = " ".join(re.sub(r"<[^>]+>", " ", sec).split())
    for name, nums in RESULTS.items():
        ok(all(n in words for n in nums), f"{name}: {', '.join(nums)}")
    links = re.findall(r'href="([^"]+)"', sec)
    for u in links:
        ok(status(u) == 200, f"{status(u)} {u}")
    lines.append(f"FAIL test_where_it_fails: {fails} check(s) failed" if fails else
                 f"PASS test_where_it_fails: {len(RESULTS)} results with their numbers, {len(links)} links all 200 (H7 not run: Qloo 429)")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
