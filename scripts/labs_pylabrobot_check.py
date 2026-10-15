"""Re-run the robotics example on a REAL PyLabRobot install and compare with the recorded fixture.

    KNOS_PYLABROBOT_PYTHON=/path/to/venv/bin/python PYTHONPATH=src python scripts/labs_pylabrobot_check.py

The venv needs `pip install pylabrobot==0.2.2`. Exit 0 when every live run matches the recorded one (the tests replay
the recording, src/knos/labs/fixtures/pylabrobot.json); exit 1 on a difference; exit 2 when PyLabRobot is not installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knos.labs import LabError, robotics  # noqa: E402

EX = ROOT / "examples" / "labs" / "robotics"


def main() -> int:
    if robotics.python() is None:
        print("PyLabRobot is not installed: name a venv with pylabrobot==0.2.2 in KNOS_PYLABROBOT_PYTHON", file=sys.stderr)
        return 2
    rec, live = robotics.PyLabRobot("fixture"), robotics.PyLabRobot("live")
    bad = 0
    for name in ("serial_dilution.py", "serial_dilution_wrong.py"):
        try:
            want = rec.run_once(EX / name, EX / "sealed_test.json")
            got = live.run_once(EX / name, EX / "sealed_test.json")
        except LabError as why:
            print(f"{name}: {why}", file=sys.stderr)
            return 1
        same = {k: got[k] for k in ("final", "max_abs_error_ul", "error")} == {k: want[k] for k in ("final", "max_abs_error_ul", "error")}
        print(f"{name}: live max error {got['max_abs_error_ul']} uL on PyLabRobot {got['pylabrobot']}: {'matches' if same else 'DIFFERS from'} the recording")
        bad += not same
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
