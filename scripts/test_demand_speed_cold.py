"""test_demand_speed_cold, live: after a redeploy (the app's Qloo cache empty), one warm-up request with a different
text, then 20 ideas never checked before, once each and in sequence, against the live demand check (POST /api/check),
each timed from the request sent to the full response read. p95 is the 19th of the 20 sorted times (nearest rank).
Pass: p95 at most 10.0 s. Reports p50, p95, max and how many ideas had heatmap cells.

    python scripts/test_demand_speed_cold.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

APP = "https://knos.onrender.com"
OUT = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world") / "test_demand_speed_cold.txt"
WARM = "a ceramic mug that keeps coffee warm"
IDEAS = ["a folding e-bike for apartment renters", "a sourdough starter subscription", "a meditation app for night-shift nurses",
         "vegan leather sneakers", "a board game about climate negotiation", "a podcast about West African jazz",
         "a dog-walking app for seniors", "a skincare line for teenage boys", "a budget travel guide to Japan",
         "a K-pop dance class studio", "a smart plant pot that texts you", "an anime-themed cafe", "handmade surfboards",
         "a chess coaching app for kids", "an indie horror film festival", "a low-sugar craft soda",
         "a vintage camera repair shop", "a yoga retreat in Portugal", "a true-crime book club", "a solar phone charger for hikers"]


def timed(idea: str) -> tuple[float, dict]:
    req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": idea}).encode(), {"Content-Type": "application/json", "User-Agent": "knos-test"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    return time.perf_counter() - t0, json.loads(body)


def main() -> int:
    warm, _ = timed(WARM)
    lines = [f"warm-up {warm:.2f} s ({WARM})"]
    times, cells = [], 0
    for idea in IDEAS:
        s, rep = timed(idea)
        n = (rep.get("terms") or {}).get("heatmap_cells") or len(rep.get("where") or [])
        cells += n > 0
        slow = sorted((c for c in rep.get("calls") or [] if isinstance(c.get("ms"), (int, float))), key=lambda c: -c["ms"])[:1]
        times.append(s)
        lines.append(f"{s:6.2f} s  {n:2} cells  {idea}" + (f"  (slowest call: {slow[0]['what'][:50]}, {slow[0]['ms']} ms)" if slow else ""))
    srt = sorted(times)
    p95, p50 = srt[math.ceil(0.95 * len(srt)) - 1], srt[math.ceil(0.50 * len(srt)) - 1]
    ok = len(times) == 20 and p95 <= 10.0
    lines.append(f"{'PASS' if ok else 'FAIL'} test_demand_speed_cold: p95 {p95:.2f} s over 20 never-checked ideas after a redeploy "
                 f"(at most 10.0), p50 {p50:.2f} s, max {srt[-1]:.2f} s, {cells} of 20 with heatmap cells")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
