"""test_outside_counter, live: the invite page and its share link exist; the counter equals the store it sums; a
run by an automated client (this script) is not counted; the open call is in Knos's own README and in one
Discussions post, nowhere else posted by Knos.

    python scripts/test_outside_counter.py [https://knos.onrender.com]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://knos.onrender.com"
fails = []


def ok(cond: bool, what: str, extra=None) -> None:
    print(("ok   " if cond else "FAIL ") + what + (f" {json.dumps(extra)}" if extra is not None else ""))
    if not cond:
        fails.append(what)


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        body = r.read()
        return json.loads(body) if path.startswith("/api/") else body.decode("utf-8")


page = get("/invite")
ok('id="counter"' in page and 'id="share"' in page and "/invite" in page and "/api/outside" in page,
   "the invite page shows the live counter and a share link")
before = get("/api/outside")
rows = get("/api/outside/rows")["rows"]
ok(before["rows"] == len(rows) and before["crossings"] == sum(r["kind"] == "crossing" for r in rows)
   and before["commitments"] == sum(r["kind"] == "commitment" for r in rows), "the counter equals the rows of the store", before)
req = urllib.request.Request(BASE + "/api/cross", json.dumps({"idea": "a smart water bottle that glows to remind you to drink"}).encode(),
                             {"Content-Type": "application/json", "User-Agent": "python-urllib/3.12 (knos test_outside_counter)"}, method="POST")
urllib.request.urlopen(req, timeout=60).read()
time.sleep(3)
after = get("/api/outside")
ok(after["crossings"] == before["crossings"], "a crossing by an automated client is not counted", {"before": before["crossings"], "after": after["crossings"]})
ok(all(set(r) == {"kind", "at", "ref", "via"} for r in rows), "a row keeps no personal data (kind, time, id, via)")
readme = urllib.request.urlopen("https://raw.githubusercontent.com/drexthealpha/Knos/main/README.md", timeout=60).read().decode()
ok("Open call" in readme and "knos.onrender.com/invite" in readme, "the open call is in Knos's README")
d = json.loads(subprocess.run(["gh", "api", "graphql", "-f", 'query={repository(owner:"drexthealpha",name:"Knos"){discussions(first:50){nodes{title url}}}}'],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout)["data"]["repository"]["discussions"]["nodes"]
calls = [x for x in d if x["title"].startswith("Open call")]
ok(len(calls) == 1, "one Discussions post carries the open call", [x["url"] for x in calls])
print(f"outside so far: {after['crossings']} crossings, {after['commitments']} commitments ({after['rows']} rows)")
print("PASS test_outside_counter" if not fails else f"FAIL test_outside_counter ({len(fails)})")
sys.exit(1 if fails else 0)
