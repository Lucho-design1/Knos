"""The relayer's devnet SOL in /api/status, with an alert below 0.5 SOL (a release failed at 0.00083 SOL on 24 Oct 2026)."""
from __future__ import annotations

import sys
import types

from solders.keypair import Keypair

from knos_wanted import escrow, preorder


def _chain(lamports: int, monkeypatch):
    fake = types.ModuleType("knos.chain")
    fake.call = lambda url, method, params, **kw: {"value": lamports}          # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "knos.chain", fake)
    import knos
    monkeypatch.setattr(knos, "chain", fake, raising=False)


def _setup(monkeypatch, lamports: int):
    kp = Keypair()
    monkeypatch.setattr(preorder, "relayer", lambda: kp)
    monkeypatch.setattr(escrow, "ledger", lambda: types.SimpleNamespace(url="https://api.devnet.solana.com"))
    _chain(lamports, monkeypatch)
    preorder._funds.clear()
    return kp


def test_a_relayer_under_half_a_sol_raises_the_alert(monkeypatch, capsys):
    kp = _setup(monkeypatch, 832_920)
    got = preorder.relayer_funds()
    assert got["read"] and got["address"] == str(kp.pubkey()) and got["sol"] == 0.000833 and got["low"]
    assert "top it up" in got["alert"] and "under 0.5" in capsys.readouterr().err


def test_a_funded_relayer_has_no_alert_and_is_read_once_a_minute(monkeypatch):
    _setup(monkeypatch, 2_000_000_000)
    first = preorder.relayer_funds()
    _chain(1, monkeypatch)                                   # a second read inside a minute is the cached one
    assert first == preorder.relayer_funds() and not first["low"] and "alert" not in first


def test_no_wallet_is_said_not_guessed(monkeypatch):
    preorder._funds.clear()
    monkeypatch.setattr(preorder, "relayer", lambda: (_ for _ in ()).throw(escrow.EscrowUnavailable("no devnet test wallet configured")))
    got = preorder.relayer_funds()
    assert got["read"] is False and "no devnet test wallet" in got["why"]
