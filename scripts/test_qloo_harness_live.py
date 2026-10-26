"""test_qloo_harness_live, live: the 20 ideas of the Qloo comparison, each a demand check on the hosted app, and every
Qloo call of their reports sorted by what answered it: Qloo's harness (`qloo api mcp`), or the REST API. A call the
harness can take (qloo_harness.mapped) that REST answered is a fallback. The container's memory (/api/ops/memory, every
process) is sampled before, during and after. Pass: 20 of 20 ideas with harness answers, 0 fallbacks, peak under 400 MB.

    KNOS_ADMIN_KEY=... python scripts/test_qloo_harness_live.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "apps" / "wanted")]
from qloo_vs_open_signals import IDEAS  # noqa: E402
from knos_wanted import qloo_harness  # noqa: E402

APP = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com").rstrip("/")
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
H = {"Content-Type": "application/json", "X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}
PEAK_MB = 400.0


def get(path: str, body: dict | None = None, timeout: int = 300) -> dict:
    req = urllib.request.Request(APP + path, json.dumps(body).encode() if body else None, H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> int:
    seen, stop = [], threading.Event()

    def sample():
        while not stop.is_set():
            try:
                seen.append(get("/api/ops/memory", timeout=30)["all_processes_mb"])
            except Exception:  # noqa: BLE001 - an instance that does not answer is in the result as None
                seen.append(None)
            stop.wait(5)
    t = threading.Thread(target=sample, daemon=True)
    t.start()
    lines, with_harness, fallbacks = [], 0, 0
    for _, idea in IDEAS:
        try:
            rep = get("/api/check", {"idea": idea})
        except Exception as e:  # noqa: BLE001
            lines.append(f"{idea[:44]:44} no report: {type(e).__name__}")
            continue
        h = r = f = 0
        for c in rep.get("calls") or []:
            if c.get("error"):
                continue
            path = str(c.get("call", "")).split(" ", 1)[-1]
            if c.get("surface") == qloo_harness.SURFACE:
                h += 1
            else:
                r += 1
                f += qloo_harness.mapped(path, c.get("params") or {}) is not None
        with_harness += h > 0
        fallbacks += f
        lines.append(f"{idea[:44]:44} harness {h}, REST {r}, of them fallbacks {f}")
    stop.set()
    t.join(10)
    st = get("/api/status").get("qloo_rest", {}).get("harness_first") or {}
    peak = max([x for x in seen if isinstance(x, (int, float))], default=None)
    died = sum(1 for x in seen if x is None)
    ok = with_harness == len(IDEAS) and fallbacks == 0 and peak is not None and peak < PEAK_MB and died == 0
    lines.append(f"harness answered {st.get('answered')} calls since start; memory samples {len(seen)}, peak {peak} MB, {died} without answer")
    lines.append(("PASS" if ok else "FAIL") + f" test_qloo_harness_live: {with_harness} of {len(IDEAS)} ideas through the harness, "
                 f"{fallbacks} REST fallbacks, container peak {peak} MB (under {PEAK_MB:g})")
    print("\n".join(lines))
    (WORLD / "test_qloo_harness_live.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
