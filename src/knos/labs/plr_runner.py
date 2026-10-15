"""Run one liquid-handling protocol on PyLabRobot's simulator and score it against a sealed test. Standalone: it imports
nothing from Knos, so it runs under any Python that has `pylabrobot` (pinned 0.2.2; checked 14 Oct 2026).

    python plr_runner.py PROTOCOL.py SEALED.json      ->  one JSON line on stdout

PROTOCOL.py defines `async def protocol(lh, plate, tips)`: the researcher's submission. The deck is the one from
PyLabRobot's docs (STARLet deck, LiquidHandlerChatterboxBackend, a Hamilton 1000 uL filter tip rack, a Corning 96-well
plate), with tip and volume tracking on, so every aspiration and dispense moves tracked volume. SEALED.json holds the
starting volumes and the volumes every checked well must end with: the researcher never sees it.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import sys


def score(final: dict, expected: dict, tolerance_ul: float) -> dict:
    """The sealed test's measurements: the largest error over the checked wells, and how many are within tolerance."""
    errors = {w: abs(float(final.get(w, 0.0)) - float(v)) for w, v in expected.items()}
    worst = max(errors.values()) if errors else 0.0
    return {"max_abs_error_ul": round(worst, 6), "wells_checked": len(errors),
            "wells_within_tolerance": sum(1 for e in errors.values() if e <= tolerance_ul)}


async def _run(protocol_path: str, sealed: dict) -> dict:
    import pylabrobot
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
    from pylabrobot.resources import (PLT_CAR_L5AC_A00, TIP_CAR_480_A00, cor_96_wellplate_360uL_Fb, hamilton_96_tiprack_1000uL_filter,
                                      set_tip_tracking, set_volume_tracking)
    from pylabrobot.resources.hamilton import STARLetDeck

    spec = importlib.util.spec_from_file_location("knos_submitted_protocol", protocol_path)
    assert spec is not None and spec.loader is not None, f"not a Python file: {protocol_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    set_tip_tracking(True)
    set_volume_tracking(True)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        lh = LiquidHandler(backend=LiquidHandlerChatterboxBackend(num_channels=8), deck=STARLetDeck())
        await lh.setup()
        tip_car = TIP_CAR_480_A00(name="tip_carrier")
        tip_car[0] = tips = hamilton_96_tiprack_1000uL_filter(name="tips_01")
        lh.deck.assign_child_resource(tip_car, rails=15)
        plt_car = PLT_CAR_L5AC_A00(name="plate_carrier")
        plt_car[0] = plate = cor_96_wellplate_360uL_Fb(name="plate_01")
        lh.deck.assign_child_resource(plt_car, rails=8)
        plate.set_well_volumes([float(sealed["start"].get(w.get_identifier(), 0.0)) for w in plate.get_all_items()])
        error = None
        try:
            await mod.protocol(lh, plate, tips)
        except Exception as why:  # noqa: BLE001 - a protocol that crashes is a result too
            error = f"{type(why).__name__}: {why}"
        final = {w.get_identifier(): w.tracker.get_used_volume() for w in plate.get_all_items()}
        await lh.stop()
    ops = sum(1 for line in log.getvalue().splitlines() if line.strip().endswith(":") and not line.startswith(" "))
    return {"pylabrobot": pylabrobot.__version__, "backend": "LiquidHandlerChatterboxBackend", "deck": "STARLetDeck",
            "error": error, "operations": ops, "final": {w: final[w] for w in sorted(sealed["expected"])},
            **score(final, sealed["expected"], float(sealed.get("tolerance_ul", 0.5)))}


def main(argv: list[str]) -> int:
    protocol_path, sealed_path = argv[1], argv[2]
    with open(sealed_path, encoding="utf-8") as f:
        sealed = json.load(f)
    print(json.dumps(asyncio.run(_run(protocol_path, sealed)), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
