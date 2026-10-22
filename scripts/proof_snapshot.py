"""The proof shown first on the front door (TASK-CHAMPION T3): the app's latest real check (GET /api/proof), written
into the built page so the card is there at the first paint, labelled with the time the app ran it. It is the built
site's data, like stats.json: never in the repository (Qloo's answers stay on the app's server and in what it serves).

    python scripts/proof_snapshot.py _site/index.html [https://knos.onrender.com]

No answer (the app asleep or down): the page keeps `null` and the card is asked for when it is on screen.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

SLOT = '<script type="application/json" id="k-proof">null</script>'


def fetch(app: str) -> dict | None:
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(app + "/api/proof", headers={"User-Agent": "knos proof_snapshot"}), timeout=60) as r:
                p = json.loads(r.read()).get("proof")
                return p if isinstance(p, dict) and p.get("hash") else None
        except (OSError, ValueError):
            time.sleep(10)
    return None


def main(argv: list[str]) -> int:
    page, app = Path(argv[0]), (argv[1] if len(argv) > 1 else "https://knos.onrender.com").rstrip("/")
    html = page.read_text(encoding="utf-8")
    if SLOT not in html:
        print(f"{page}: no proof slot")
        return 1
    p = fetch(app)
    if p is None:
        print("proof snapshot: the app gave none; the page asks for it when shown")
        return 0
    data = json.dumps(p, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page.write_text(html.replace(SLOT, f'<script type="application/json" id="k-proof">{data}</script>', 1), encoding="utf-8", newline="\n")
    print(f"proof snapshot: {p.get('idea')!r}, checked {p.get('checked_at')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
