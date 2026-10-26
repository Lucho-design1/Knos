"""test_warm: the hosted app stays awake. The warm workflow (.github/workflows/warm.yml) asks /healthz every 600 s and
logs each probe as `PROBE <UTC time> <HTTP status> <seconds to first byte>`; this reads the probes back from GitHub's
logs of its runs and takes the newest 144 (24 hours). Pass: 144 probes, each 540 to 660 s after the one before,
0 cold starts (an answer that is not 200, or a first byte after 10 s: Render's wake-up takes 20 s or more), and a 95th
percentile first byte of 2 s or less.

    python scripts/test_warm.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = "drexthealpha/Knos"
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
N, GAP, COLD_S, P95_S = 144, (540, 660), 10.0, 2.0
PROBE = re.compile(r"PROBE (\S+) (\d{3}) ([\d.]+)")


def gh(*a: str) -> str:
    return subprocess.run(["gh", *a], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or ""


def main() -> int:
    runs = json.loads(gh("run", "list", "-R", REPO, "-w", "warm.yml", "-L", "40", "--json", "databaseId,status") or "[]")
    probes: dict[str, tuple[int, float]] = {}
    for r in runs:
        for line in gh("run", "view", str(r["databaseId"]), "-R", REPO, "--log").splitlines():
            m = PROBE.search(line)
            if m:
                probes[m.group(1)] = (int(m.group(2)), float(m.group(3)))
    seq = sorted(probes.items())[-N:]
    times = [dt.datetime.fromisoformat(t.replace("Z", "+00:00")) for t, _ in seq]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    off = [g for g in gaps if not GAP[0] <= g <= GAP[1]]
    cold = [(t, c, s) for t, (c, s) in seq if c != 200 or s > COLD_S]
    ttfb = sorted(s for _, (_, s) in seq)
    p95 = ttfb[max(0, math.ceil(0.95 * len(ttfb)) - 1)] if ttfb else None
    ok = len(seq) == N and not off and not cold and p95 is not None and p95 <= P95_S
    lines = [f"{len(probes)} probes in {len(runs)} runs; the newest {len(seq)}: {seq[0][0] if seq else '-'} to {seq[-1][0] if seq else '-'}",
             f"gaps outside {GAP[0]} to {GAP[1]} s: {len(off)} {off[:5]}; cold starts: {len(cold)} {cold[:5]}",
             ("PASS" if ok else "FAIL") + f" test_warm: {len(seq)} of {N} probes, {len(off)} gaps off 10 minutes, {len(cold)} cold starts, "
             f"p95 first byte {p95 if p95 is None else round(p95, 3)} s (at most {P95_S:g})"]
    print("\n".join(lines))
    (WORLD / "test_warm.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
