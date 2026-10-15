"""Robotics: a lab protocol is judged on PyLabRobot's simulator first, as a sealed test, and re-run independently.

PyLabRobot (github.com/PyLabRobot/pylabrobot; PyPI `pylabrobot` 0.2.2, 30 Jul 2026, the latest stable on 14 Oct 2026)
drives real liquid handlers (Hamilton, Tecan, Opentrons) from Python, and the SAME protocol runs on its
LiquidHandlerChatterboxBackend with tip and volume tracking. So a protocol a robot lab will run can be checked before
the lab is paid to run it:

    LAB verdict      the protocol ran as specified on the simulator: no crash, every re-run agrees exactly (same final
                     volumes), the recorded PyLabRobot version and backend
    OUTCOME verdict  the sealed test: every checked well ends within tolerance of the volume the sealed test expects
                     (`max_abs_error_ul` <= tolerance). The researcher never sees the expected volumes.

The run happens in a separate process (knos/labs/plr_runner.py) under the Python named by $KNOS_PYLABROBOT_PYTHON (a
venv with `pylabrobot==0.2.2`), else this Python when it has pylabrobot (live mode). Fixture mode, the default and
every test, replays fixtures/pylabrobot.json: the runner's output RECORDED from real runs of the example protocols
(scripts/labs_pylabrobot_check.py re-runs them on a real install and compares). Nothing is bought; the same sealed test then
spot-checks the physical run's volumes (Leitner: a new robot lab on every order).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Adapter, LabError, Order, Quote, Results, Spec, Status, canonical, sha256_hex

RUNNER = Path(__file__).with_name("plr_runner.py")
FIXTURE = Path(__file__).with_name("fixtures") / "pylabrobot.json"
PIN = "0.2.2"


def python() -> str | None:
    named = os.environ.get("KNOS_PYLABROBOT_PYTHON")
    if named and Path(named).exists():
        return named
    try:
        import pylabrobot  # noqa: F401
        return sys.executable
    except ImportError:
        return None


class PyLabRobot(Adapter):
    NAME = "pylabrobot"
    FIELD = "robotics"
    KEY_ENV = None
    BASE = "local"
    DOCS = "https://docs.pylabrobot.org"
    LIVE_READY = True
    ORDERS = False

    def __init__(self, mode: str = "fixture", transport=None, key: str | None = None, base: str | None = None):
        if mode not in ("fixture", "live"):
            raise LabError("mode: fixture or live")
        self.mode, self.base, self._key, self.fixtures, self.transport = mode, "local", None, None, None
        self.recorded = json.loads(FIXTURE.read_text(encoding="utf-8")) if mode == "fixture" else None
        self.done: dict[str, Results] = {}

    @property
    def label(self) -> str:
        if self.recorded is not None:
            return self.recorded["label"]
        return f"simulation: PyLabRobot {PIN} LiquidHandlerChatterboxBackend (local re-runs; no lab, no money)"

    @staticmethod
    def files(spec: Spec) -> tuple[Path, Path]:
        p, s = spec.protocol.get("protocol_file"), spec.protocol.get("sealed_test")
        if not p or not s or not Path(p).is_file() or not Path(s).is_file():
            raise LabError("protocol.protocol_file and protocol.sealed_test: the submitted protocol (.py) and the sealed test (.json)")
        return Path(p), Path(s)

    def quote(self, spec: Spec) -> Quote:
        self.files(spec)
        return Quote(self.NAME, "0.00", "USD", 0, None, None, [{"what": "simulated re-runs"}], [], self.is_fixture, self.label)

    def order(self, spec: Spec, escrow_ref: str, quote: Quote | None = None) -> Order:
        p, s = self.files(spec)
        oid = "plr-" + sha256_hex(p.read_bytes() + s.read_bytes())[:16]
        return Order(self.NAME, oid, escrow_ref, spec.hash(), "submitted", self.is_fixture, self.label,
                     {"protocol_sha256": sha256_hex(p.read_bytes()), "sealed_sha256": sha256_hex(s.read_bytes())})

    def status(self, order: Order) -> Status:
        st = "completed" if order.order_id in self.done else "submitted"
        return Status(self.NAME, order.order_id, st, st, self.is_fixture, self.label)

    def run_once(self, protocol: Path, sealed: Path, timeout: int = 300) -> dict:
        """One simulator run: in fixture mode the RECORDED run of this exact protocol and sealed test (by their
        sha256), never an invented one; in live mode a fresh run under PyLabRobot."""
        if self.recorded is not None:
            key = f"{sha256_hex(protocol.read_bytes())}:{sha256_hex(sealed.read_bytes())}"
            if key not in self.recorded["runs"]:
                raise LabError("no recorded PyLabRobot run for this protocol and sealed test: run it live (KNOS_PYLABROBOT_PYTHON)")
            return dict(self.recorded["runs"][key])
        py = python()
        if py is None:
            raise LabError("PyLabRobot is not installed: make a venv with `pip install pylabrobot==0.2.2` and name its python in KNOS_PYLABROBOT_PYTHON")
        env = {k: v for k, v in os.environ.items() if not k.endswith(("_KEY", "_TOKEN", "_SECRET"))}   # the protocol never sees a key
        with tempfile.TemporaryDirectory() as tmp:
            got = subprocess.run([py, str(RUNNER), str(protocol), str(sealed)], capture_output=True, text=True, timeout=timeout, cwd=tmp, env=env)
        if got.returncode != 0:
            raise LabError(f"the simulator run failed: {got.stderr.strip()[-300:]}")
        return json.loads(got.stdout.strip().splitlines()[-1])

    def results(self, order: Order, spec: Spec | None = None) -> Results:
        if spec is None:
            raise LabError("pylabrobot: results(order, spec): the spec names the files")
        p, s = self.files(spec)
        n = int(spec.protocol.get("reruns", 2))
        runs = []
        for i in range(n):
            r = self.run_once(p, s)
            runs.append({"id": f"rerun-{i + 1}", "ok": r["error"] is None, "why": r["error"],
                         "measurements": {k: r[k] for k in ("max_abs_error_ul", "wells_checked", "wells_within_tolerance", "operations")},
                         "final": r["final"], "pylabrobot": r["pylabrobot"]})
        agree = len({json.dumps(x["final"], sort_keys=True) for x in runs}) == 1
        versions = sorted({x["pylabrobot"] for x in runs})
        why = ([] if agree else ["the re-runs disagree"]) + ([] if all(x["ok"] for x in runs) else ["the protocol crashed"])
        qc = {"passed": not why, "why": "; ".join(why) or None, "reruns": n, "reruns_agree": agree, "pylabrobot": versions, "rule": "knos"}
        out = Results(self.NAME, order.order_id, "completed", runs, qc,
                      [{"name": p.name, "sha256": sha256_hex(p.read_bytes())}, {"name": "reruns.json", "sha256": sha256_hex(canonical(runs))}],
                      {"backend": "LiquidHandlerChatterboxBackend", "deck": "STARLetDeck", "pylabrobot": versions[0] if versions else None,
                       "reruns": n}, self.is_fixture, self.label)
        self.done[order.order_id] = out
        return out
