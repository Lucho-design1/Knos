"""`knos game pot` shows the split the pay path pays: proven players only; an unproven claimant "plays, not paid"."""
from __future__ import annotations

from test_game_fix34b import TORVALDS, W1, W2, Chainless, _finished

from knos.game import payout
from knos.game.cli import pot_report


def test_pot_shows_the_same_proven_split_as_the_pay_path(tmp_path):
    g, pids = _finished(tmp_path, [("torvalds", {"github_id": TORVALDS, "payee": W1}), ("ada", {"github_id": 2, "payee": W2})])
    led = Chainless({2: W2})
    out = pot_report(g, lambda: led)
    paid = [(p["player"], p["bps"]) for p in out["split"]["parts"]]
    assert paid == [(pids["ada"], 10_000)]
    assert [(r[0], r[1]) for r in payout.payees(led, g)["payees"]] == [(2, 10_000)]          # the pay path agrees
    by = {r["name"]: r for r in out["players"]}
    assert by["torvalds"]["status"] == "plays, not paid" and by["torvalds"]["proven"] is False
    assert by["ada"]["status"] == "paid 10000 bps" and by["ada"]["proven"] is True


def test_pot_shows_no_split_when_the_chain_cannot_be_read(tmp_path):
    g, _ = _finished(tmp_path, [("ada", {"github_id": 2, "payee": W2})])

    def down():
        raise OSError("rpc down")
    out = pot_report(g, down)
    assert out["split"] is None and "rpc down" in out["chain_error"] and out["players"][0]["proven"] is None
