"""test_demand_speed, live: one warm-up request, then the 20 T2 ideas in sequence against the live app's demand check
(POST /api/check), each timed from the request sent to the full response read. p95 is the 19th of the 20 times
sorted (nearest rank). Pass: p95 at most 10.0 s.

    python scripts/test_demand_speed.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_qloo_sets_terms import APP, ideas  # noqa: E402

OUT = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world")) / "test_demand_speed.txt"


def timed(idea: str) -> float:
    req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": idea}).encode(), {"Content-Type": "application/json", "User-Agent": "knos-test"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        r.read()
    return time.perf_counter() - t0


def main() -> int:
    warm = timed("a reusable coffee cup that keeps drinks hot")
    lines = [f"warm-up {warm:.2f} s"]
    times = []
    for idea in ideas():
        s = timed(idea)
        times.append(s)
        lines.append(f"{s:6.2f} s  {idea}")
    srt = sorted(times)
    p95 = srt[math.ceil(0.95 * len(srt)) - 1]
    ok = len(times) == 20 and p95 <= 10.0
    lines.append(f"{'PASS' if ok else 'FAIL'} test_demand_speed: p95 {p95:.2f} s over {len(times)} T2 ideas (at most 10.0), median {srt[len(srt) // 2]:.2f} s, max {srt[-1]:.2f} s")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
