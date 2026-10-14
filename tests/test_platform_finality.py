"""Finality is one setting (knos.platform.finality, KNOS_COMMITMENT): processed, confirmed or finalized."""
from __future__ import annotations

import pytest

from knos import chain
from knos.platform import finality


def test_the_default_is_confirmed_and_the_setting_takes_the_three_words(monkeypatch):
    monkeypatch.delenv("KNOS_COMMITMENT", raising=False)
    assert finality.commitment() == "confirmed"
    for word in ("processed", "confirmed", "finalized", " Finalized "):
        monkeypatch.setenv("KNOS_COMMITMENT", word)
        assert finality.commitment() == word.strip().lower()
    monkeypatch.setenv("KNOS_COMMITMENT", "rooted")
    with pytest.raises(ValueError):
        finality.commitment()


def test_a_deeper_status_satisfies_a_shallower_commitment_and_never_the_reverse():
    assert finality.good("processed") == ("processed", "confirmed", "finalized")
    assert finality.good("confirmed") == ("confirmed", "finalized")
    assert finality.good("finalized") == ("finalized",)
    st = lambda s: {"confirmationStatus": s, "err": None}  # noqa: E731
    assert finality.reached(st("processed"), "processed") and not finality.reached(st("processed"), "confirmed")
    assert finality.reached(st("finalized"), "confirmed") and not finality.reached(None, "processed")


def test_the_ledger_waits_for_the_setting(monkeypatch):
    monkeypatch.setenv("KNOS_COMMITMENT", "processed")
    assert chain.Ledger("http://127.0.0.1:1").commitment == "processed"
    monkeypatch.setenv("KNOS_COMMITMENT", "finalized")
    assert chain.Ledger("http://127.0.0.1:1").commitment == "finalized"
    assert chain.Ledger("http://127.0.0.1:1", commitment="confirmed").commitment == "confirmed"
    # wait_all counts a processed status only when the setting asks for processed
    answers = {"processed": [{"confirmationStatus": "processed", "err": None}]}
    monkeypatch.setattr(chain, "call", lambda url, method, params, timeout=10.0: {"value": answers["processed"]})
    assert chain.wait_all("u", ["s"], 1.0, "processed")[0]["confirmationStatus"] == "processed"
    with pytest.raises(TimeoutError):
        chain.wait_all("u", ["s"], 0.0, "confirmed")


def test_the_relay_asks_the_cluster_for_rent(monkeypatch):
    from knos.settle.v2.relay import wallets

    class L:
        def rent(self, size):
            return 5_080 * (128 + size)        # devnet's rate on 13 Oct 2026 (solana rent, Agave 4.4.0-beta.0)

    class Dead:
        def rent(self, size):
            raise ConnectionError

    assert wallets._rent(165, L()) == 5_080 * 293 < wallets._rent(165) == 6_960 * 293
    assert wallets._rent(165, Dead()) == wallets._rent(165, None) == 6_960 * 293
