"""test_receipt_v2: the receipt's trust line says the 8-day time lock. In this repository's numbering
the new format is receipt version 6 and the kit that adds its vectors is conformance kit 5 (versions 1 to 5 and kit 4
already existed): new receipts are version 6 with the true line, the vectors of every version pass, and
test_public_words passes with receipts of versions 1 to 5 as the only places the old delay stands.

    python scripts/test_receipt_v2.py
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "conformance"), str(ROOT / "scripts")]
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_receipt_v2.txt"


def main() -> int:
    from knos import bundle, flow, receipt as rc
    import run as kit
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    v6 = json.loads((ROOT / "docs" / "receipt" / "vectors.v6.json").read_text(encoding="utf-8"))
    new = [v["receipt"] for v in v6["valid_v6"]]
    ok("rc.build6(rc.build5(" in inspect.getsource(bundle) and "rc.build6(rc.build5(" in inspect.getsource(flow),
       "new receipts are version 6: knos bundle and the flow's receipt write build6(build5(...))")
    ok(all(r["version"] == 6 and rc.OLD_TRUST not in r["trust_remaining"] for r in new) and any(rc.NEW_TRUST in r["trust_remaining"] for r in new),
       f'version 6 receipts say "{rc.NEW_TRUST[-55:]}" and never the old delay')
    py = [sys.executable, str(ROOT / "conformance" / "impl" / "knos_python.py")]
    res = kit.run(py)
    by = {f: (x["cases"], x["passed"], len(x["failed"])) for f, x in res["formats"].items()}
    ok(all(by[f][2] == 0 and by[f][0] == by[f][1] for f in ("receipt", "receipt4", "receipt5", "receipt6")),
       f"conformance kit {res['kit']}, Python: receipt (v1-3) {by['receipt']}, receipt4 {by['receipt4']}, receipt5 {by['receipt5']}, receipt6 {by['receipt6']} (cases, passed, failed)")
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_receipt_v6.py", "tests/test_conformance.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1200)
    ok(t.returncode == 0, f"tests/test_receipt_v6.py and tests/test_conformance.py: {t.stdout.strip().splitlines()[-1] if t.stdout.strip() else t.stderr[-200:]}")
    w = subprocess.run([sys.executable, str(ROOT / "scripts" / "test_public_words.py")], cwd=ROOT, capture_output=True, text=True, timeout=600)
    ok(w.returncode == 0, f"test_public_words reran: {w.stdout.strip().splitlines()[-1] if w.stdout.strip() else w.stderr[-200:]}")
    lines.append(f"FAIL test_receipt_v2: {fails} check(s) failed" if fails else
                 f"PASS test_receipt_v2: new receipts are version 6 with the 8-day time lock; vectors of versions 1 to 6 pass ({sum(by[f][1] for f in by if f.startswith('receipt'))} receipt cases); test_public_words passes")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
