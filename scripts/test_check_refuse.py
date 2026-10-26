"""test_check_refuse, live: the demand check applies the Ready check's published refuse list (knos.refuse) before any
Qloo call. 30 ideas built from the list's own words (29 plus "a titanium machine gun barrel") get no OPEN verdict, and
the 20 ideas of the Qloo comparison keep the verdicts they had before (saved once with --baseline).

    KNOS_ADMIN_KEY=... python scripts/test_check_refuse.py [--baseline]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from knos import refuse  # noqa: E402
from qloo_vs_open_signals import IDEAS  # noqa: E402

APP = "https://knos.onrender.com"
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
BASE = WORLD / "check_refuse_baseline.json"
OP = {"X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}


def check(idea: str) -> tuple[int, str | None]:
    req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": idea}).encode(), {"Content-Type": "application/json", **OP})
    try:
        rep = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return 200, (rep.get("decision") or {}).get("verdict")
    except urllib.error.HTTPError as e:
        return e.code, None


def refuse_ideas() -> list[str]:
    out = ["a titanium machine gun barrel"]
    for cat, words in refuse.REFUSE.items():
        for w in words[:8 if cat != "sanctioned_places" else 5]:
            out.append(f"a water filter for {w.title()}" if cat == "sanctioned_places" else f"a product named for {w}")
    return out[:30]


def main(argv: list[str]) -> int:
    verdicts = {idea: check(idea)[1] for _, idea in IDEAS}
    if "--baseline" in argv:
        BASE.write_text(json.dumps(verdicts, indent=1), encoding="utf-8")
        print(f"baseline: {sum(v is not None for v in verdicts.values())} of {len(verdicts)} verdicts saved to {BASE}")
        return 0
    before = json.loads(BASE.read_text(encoding="utf-8"))
    changed = [i for i in verdicts if verdicts[i] != before.get(i)]
    bad = refuse_ideas()
    opened = [i for i in bad if check(i)[1] == "OPEN"]
    lines = [f"refuse list: {len(opened)} of {len(bad)} ideas OPEN {opened}", f"comparison ideas: {len(changed)} of {len(verdicts)} verdicts changed {changed}"]
    ok = not opened and not changed and len(bad) == 30
    lines.append(("PASS" if ok else "FAIL") + f" test_check_refuse: 0 of 30 refused ideas OPEN, {len(verdicts) - len(changed)} of 20 verdicts kept"
                 if ok else f"FAIL test_check_refuse: {len(opened)} of 30 refused ideas OPEN, {len(changed)} of 20 verdicts changed")
    print("\n".join(lines))
    (WORLD / "test_check_refuse.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
