"""The uptime log of the hosted app (TASK-QLOO-CHAMPION M7), read from GitHub's own record of the keep-warm pings.

    python scripts/uptime_log.py [--from 2026-11-02] [--to 2026-11-16] [--markdown]

.github/workflows/keepalive.yml pings https://knos.onrender.com/healthz every 5 minutes, and every run of the always-on
worker (worker.yml) pings it before it relays (docs/reference/KEEPALIVE.md). A green run is a ping the app answered. This
script lists those runs for the window, from the GitHub API (`gh api`), and says: how many ran, how many answered,
and the longest stretch with no green ping, which is the longest the app may have slept. Nothing is written by hand;
the judging period is 2 to 16 November 2026, and the log for it is this script run over that window.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys

REPO = "drexthealpha/Knos"


# both ping /healthz: the keepalive timer, and each run of the always-on worker's chain (its `healthz` step), which
# keeps the app awake when GitHub's cron skips the timer (it did, for hours, on 18 Oct 2026)
WORKFLOWS = ("keepalive.yml", "worker.yml")


def runs(since: str, until: str) -> list[dict]:
    out = []
    for wf in WORKFLOWS:
        page = 1
        while True:
            got = subprocess.run(["gh", "api", f"repos/{REPO}/actions/workflows/{wf}/runs?per_page=100&page={page}"
                                  f"&created={since}..{until}"], capture_output=True, text=True, encoding="utf-8", check=True)
            rows = json.loads(got.stdout).get("workflow_runs") or []
            out += [{"at": r["created_at"], "conclusion": r["conclusion"], "id": r["id"], "workflow": wf} for r in rows]
            if len(rows) < 100:
                break
            page += 1
    return sorted(out, key=lambda r: r["at"])


def summary(rows: list[dict], since: str, until: str) -> dict:
    t = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    green = [t(r["at"]) for r in rows if r["conclusion"] == "success"]
    edges = [t(since + "T00:00:00Z")] + green + [min(t(until + "T23:59:59Z"), dt.datetime.now(dt.timezone.utc))]
    gap = max((b - a for a, b in zip(edges, edges[1:])), default=dt.timedelta(0))
    started = edges[-1] > edges[0]          # a window that has not begun has no gap yet, not a negative one
    return {"from": since, "to": until, "runs": len(rows), "green": len(green), "failed": sum(1 for r in rows if r["conclusion"] == "failure"),
            "longest_gap_minutes": round(gap.total_seconds() / 60, 1) if started else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", default="2026-11-02")
    ap.add_argument("--to", dest="until", default="2026-11-16")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args(argv)
    rows = runs(a.since, a.until)
    s = summary(rows, a.since, a.until)
    if a.markdown:
        print(f"| From | To | Pings | Green | Failed | Longest gap (min) |\n|---|---|---|---|---|---|\n"
              f"| {s['from']} | {s['to']} | {s['runs']} | {s['green']} | {s['failed']} | {s['longest_gap_minutes']} |")
    else:
        print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
