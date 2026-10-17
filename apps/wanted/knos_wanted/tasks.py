"""Open work a contributor (person or agent) can join: the Knos game's rounds on this server, judged and paid on devnet.

The game is `knos.game` (src/knos/game): a sealed task, players who submit code, a deterministic referee, a pot paid by
verdicts. This module only fronts it for the web app: when KNOS_GAME_DIR names a game folder, /api/tasks lists its
state and /api/task/submit joins and submits in one step (the smallest honest flow: a new player per submission; the
referee answers at once; the pot is paid by the game's own verdict path at round close, not by this endpoint). Without
a game folder the page says so instead of inventing work. Open milestones are listed beside it as evidence tasks.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from . import escrow, preorder

TASK_DIR = Path(__file__).resolve().parents[3] / "examples" / "autoresearch"
DEMO_TITLE = "Demo round: beat the sealed classifier (test money)"
DEMO_LABEL = ("DEMO ROUND, devnet test money: the repository's example task, seeded by this server so contributors "
              "always have one open round; the sealed referee judges every submission")


def _status(root: Path) -> str | None:
    import json
    try:
        return json.loads((root / "game.json").read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def ensure_round() -> str | None:
    """One open demo round at a time: when no game folder is configured (or the configured one is empty or closed —
    Render wipes /data), seed a fresh labelled demo round from the task packaged in the image. Returns its id."""
    base = Path(os.environ.get("KNOS_GAME_DIR") or "").expanduser()
    if base and (base / "game.json").exists() and _status(base) != "closed":
        return None                                    # an operator's own open round: leave it alone
    if not TASK_DIR.exists():
        return None                                    # no packaged task: the page says so instead
    from knos.game.engine import Game
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    root = escrow._state_dir() / f"demo-game-{stamp}"
    g = Game.create(root, TASK_DIR, title=DEMO_TITLE, field="ml-research", game_id=f"knos-demo-{stamp}",
                    rules={"rounds": 3, "per_round": 4, "ladder_eta": 0.01, "max_refusals": 2, "identity_required": False})
    os.environ["KNOS_GAME_DIR"] = str(root)
    print(f"knos-demand-check: seeded the demo game round {g.s['id']} at {root} ({DEMO_LABEL})", flush=True)
    return g.s["id"]


def _tools():
    import importlib
    return importlib.import_module("knos.game.tools")


def available() -> tuple[bool, str]:
    if not os.environ.get("KNOS_GAME_DIR", "").strip():
        try:
            ensure_round()
        except Exception as e:  # noqa: BLE001
            return False, f"no open round: the demo round could not be seeded ({type(e).__name__})"
    if not os.environ.get("KNOS_GAME_DIR", "").strip():
        return False, "no open round on this server (no game folder and no packaged demo task)"
    try:
        _tools()
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        return False, f"the game modules are not installed here ({type(e).__name__})"


def rounds() -> list[dict]:
    ok, why = available()
    if not ok:
        return []
    gt = _tools()
    try:
        st = gt.call("knos_game_state", {})
        board = gt.call("knos_game_board", {})
    except Exception:  # noqa: BLE001
        return []
    g = st.get("game") or st
    demo = str(g.get("id") or "").startswith("knos-demo-")
    if str(g.get("status") or "") == "closed":
        try:
            ensure_round()                              # reseed: one open demo round at a time
            st = gt.call("knos_game_state", {})
            board = gt.call("knos_game_board", {})
            g, demo = st.get("game") or st, True
        except Exception:  # noqa: BLE001
            pass
    return [{"id": g.get("id"), "title": g.get("title"),
             "label": DEMO_LABEL if demo else "Knos game round: code judged by the sealed referee; the pot pays by its "
             "verdicts on devnet (test money)", "demo": demo, "state": g.get("status") or st.get("status"),
             "round": g.get("round") or st.get("round"), "players": len(board.get("board") or board.get("rows") or [])}]


def listing() -> dict:
    ok, why = available()
    ms = [{"claim_id": r.get("claim_id"), "idea": r.get("idea"), "commitment": r.get("commitment"), "units": r.get("units")}
          for r in preorder.all_public(20) if r.get("status") == "locked"]
    return {"rounds": rounds(), "why": None if ok else why, "milestones": ms,
            "note": "devnet test money; a round's pot is paid by the game's referee verdicts, a milestone by 2-of-3 referee signatures"}


def submit(round_id: str, name: str, code: str, who: str) -> dict:
    """Join the configured game as a fresh player and submit one attempt; the referee answers at once."""
    ok, why = available()
    if not ok:
        raise ValueError(why)
    if not (isinstance(code, str) and 10 <= len(code) <= 100_000):
        raise ValueError("code: your submission, 10 to 100,000 characters")
    gt = _tools()
    name = (str(name or "").strip() or "contributor")[:40]
    joined = gt.call("knos_game_join", {"name": f"{name}-{abs(hash(who)) % 10_000}", "kind": "agent" if "agent" in who else "human",
                                        "label": f"web contributor ({who[:40]})"})
    player, key = joined.get("player"), joined.get("key")
    got = gt.call("knos_game_submit", {"player": player, "key": key, "code": code})
    return {"joined": {k: joined.get(k) for k in ("player", "name")}, "result": got,
            "note": "judged by the game's sealed referee; the pot pays by verdicts at round close (devnet test money)"}
