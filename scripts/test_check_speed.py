"""test_check_speed, live: how long the hosted demand check takes, over 50 ideas: the 20 of the Qloo comparison and 30
Kickstarter projects (successful or failed, launched 2019-2023) drawn from the webrobots.io dump with seed 1, none of
them in test_kickstarter_truth's sample, so their Qloo answers are not cached yet. One check at a time, as a visitor
asks. Passes when the 95th percentile is at most 20 s and no check takes over 60 s.

    KNOS_ADMIN_KEY=... python scripts/test_check_speed.py <Kickstarter_*.json.gz> <ks-sample.json>
"""
from __future__ import annotations

import gzip
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qloo_vs_open_signals import IDEAS  # noqa: E402
from test_kickstarter_truth import FROM, KEEP, TO, _when, idea  # noqa: E402

APP = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com").rstrip("/")
WORLD = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world"))
P95_S, MAX_S, FRESH = 20.0, 60.0, 30


def fresh_ideas(dump: str, sample: str) -> list[str]:
    taken = {r["id"] for r in json.loads(Path(sample).read_text(encoding="utf-8"))["rows"]}
    pool, seen = [], set()
    with gzip.open(dump, "rt", encoding="utf-8") as f:
        for line in f:
            d = (json.loads(line) if line.strip() else {}).get("data") or {}
            pid = str(d.get("id") or "")
            if not pid or pid in seen or pid in taken or d.get("state") not in KEEP or not d.get("launched_at"):
                continue
            seen.add(pid)
            if FROM <= _when(d["launched_at"]) <= TO and d.get("blurb"):
                c = d.get("category") or {}
                pool.append({"id": pid, "name": " ".join(str(d.get("name") or "").split()), "blurb": " ".join(str(d["blurb"]).split()),
                             "category": {"main": c.get("parent_name") or c.get("name") or "?", "sub": c.get("name") or "?"}})
    pool.sort(key=lambda r: int(r["id"]) if r["id"].isdigit() else 0)
    return [idea(r) for r in random.Random(1).sample(pool, FRESH)]


def main(argv: list[str]) -> int:
    ideas = [i for _, i in IDEAS] + fresh_ideas(argv[0], argv[1])
    head = {"Content-Type": "application/json", "X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}
    lines, took = [], []
    for n, text in enumerate(ideas, 1):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": text}).encode(), head)
            with urllib.request.urlopen(req, timeout=180) as r:
                rep = json.loads(r.read())
            st, server, cached = 200, rep.get("elapsed_ms"), sum(1 for c in rep.get("calls") or [] if c.get("cached"))
            calls = len(rep.get("calls") or [])
        except urllib.error.HTTPError as e:
            st, server, cached, calls = e.code, None, 0, 0
        except OSError:
            st, server, cached, calls = 599, None, 0, 0
        s = time.monotonic() - t0
        took.append(s if st in (200, 400) else MAX_S + 1)                # no answer counts as over the limit
        lines.append(f"{n:2} {s:6.1f} s HTTP {st} server {server} ms, {cached}/{calls} cached | {text[:60]}")
        print(lines[-1], flush=True)
    xs = sorted(took)
    p95 = xs[max(0, math.ceil(0.95 * len(xs)) - 1)]
    over = sum(1 for x in xs if x > MAX_S)
    ok = p95 <= P95_S and over == 0
    lines.append(("PASS" if ok else "FAIL") + f" test_check_speed: {len(xs)} ideas, p95 {p95:.1f} s (at most {P95_S:g}), median "
                 f"{xs[len(xs) // 2]:.1f} s, max {xs[-1]:.1f} s, {over} over {MAX_S:g} s")
    print(lines[-1])
    (WORLD / "test_check_speed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
