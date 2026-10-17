"""Open work a contributor (person or agent) can join: the Knos game's rounds on this server, judged and paid on devnet.

The game is `knos.game` (src/knos/game): a sealed task, players who submit code, a deterministic referee, a pot paid by
verdicts. This module only fronts it for the web app: when KNOS_GAME_DIR names a game folder, /api/tasks lists its
state and /api/task/submit joins and submits in one step (the smallest honest flow: a new player per submission; the
referee answers at once; the pot is paid by the game's own verdict path at round close, not by this endpoint). Without
a game folder the page says so instead of inventing work. Open milestones are listed beside it as evidence tasks.
"""
from __future__ import annotations

import os

from . import preorder


def _tools():
    import importlib
    return importlib.import_module("knos.game.tools")


def available() -> tuple[bool, str]:
    if not os.environ.get("KNOS_GAME_DIR", "").strip():
        return False, "no game folder is configured on this server (KNOS_GAME_DIR)"
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
    return [{"id": g.get("id"), "title": g.get("title"), "label": "Knos game round: code judged by the sealed referee; "
             "the pot pays by its verdicts on devnet (test money)", "state": g.get("state") or st.get("state"),
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
