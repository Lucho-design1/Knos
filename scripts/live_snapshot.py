"""At the Pages build (.github/workflows/network.yml): the newest agent payout and the usage counter, read from the app
(GET /api/agent/payout/latest, GET /api/usage), written into the built front door so a reader sees them with no
request. The page asks the app again after load (web/brand/hero.js). A build never fails here: when the app does
not answer, the page keeps the line it was committed with.

    python scripts/live_snapshot.py _site/index.html
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

APP = "https://knos.onrender.com"


def get(path: str) -> dict | None:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(APP + path, headers={"User-Agent": "knos-pages-build"}), timeout=120) as r:
                return json.loads(r.read())
        except Exception as why:  # noqa: BLE001
            print(f"live_snapshot: {path}: {type(why).__name__} ({attempt + 1}/3)")
            time.sleep(10)
    return None


def paid_html(x: dict) -> str:
    day = str(x.get("at") or "")[:10]
    return (f'Agent paid <b>{html.escape(str(x["units"]))} test units</b> for verified work{", " + html.escape(day) if day else ""} · '
            f'<a href="{html.escape(x["explorer"])}" target="_blank" rel="noopener">the transaction</a>')


def usage_html(u: dict) -> str:
    e = lambda v: html.escape(str(v))  # noqa: E731
    return (f'<b data-n="checks">{e(u["checks"])}</b> demand checks · <b data-n="briefs">{e(u["briefs"])}</b> Ready briefs since {e(u["since"])} · '
            f'<b data-n="payouts">{e(u["payouts"])}</b> payment program transactions on devnet')


def main(path: str) -> int:
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    x = get("/api/agent/payout/latest")
    if x and x.get("found") and (x.get("units") or 0) > 0 and re.fullmatch(r"https://explorer\.solana\.com/tx/[1-9A-HJ-NP-Za-km-z]+\?cluster=devnet", str(x.get("explorer"))):
        s, n = re.subn(r'(<p class="k-paid" id="k-paid" data-not-prose>).*?(</p>)', lambda m: m[1] + paid_html(x) + m[2], s, count=1, flags=re.S)
        print(f"live_snapshot: payout {x['units']} units, {x.get('signature', '')[:8]}... ({n} line)")
    u = get("/api/usage")
    if u and isinstance(u.get("payouts"), int):
        s, n = re.subn(r'<p class="fine" id="k-usage" data-not-prose hidden></p>',
                       lambda _: f'<p class="fine" id="k-usage" data-not-prose>{usage_html(u)}</p>', s, count=1)
        print(f"live_snapshot: usage {u['checks']} checks, {u['briefs']} briefs, {u['payouts']} transactions ({n} line)")
    p.write_text(s, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
