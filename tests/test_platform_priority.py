"""Priority fees sized to the work (knos.platform.priority) and the WebSocket wait for a signature. Devnet proof in
docs/reference/PRIORITY_FEES.md: the same memo at 5,000 micro-lamports a unit paid 202 lamports of priority fee with
the right-sized limit, where the old 1,400,000-unit limit would have paid 7,000."""
from __future__ import annotations

import pytest
from solders.compute_budget import ID as CB
from solders.compute_budget import set_compute_unit_limit
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos import chain
from knos.platform import priority as P

MEMO = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")


def test_the_estimate_is_the_75th_percentile_of_recent_fees_capped(monkeypatch):
    assert P.pick([]) == 0 and P.pick([0, 0, 0, 0]) == 0
    assert P.pick([0, 10, 20, 30]) == 20 and P.pick([5]) == 5
    assert P.pick([10, 1_000_000]) == P.DEFAULT_MAX
    monkeypatch.setenv("KNOS_PRIORITY_MAX", "7")
    assert P.pick([100]) == 7
    monkeypatch.delenv("KNOS_PRIORITY_MAX")
    asked = []
    got = P.estimate("u", ["A", "B"], call=lambda url, m, p: asked.append((m, p)) or [{"slot": 1, "prioritizationFee": 3}, {"slot": 2, "prioritizationFee": 9}])
    assert got == 9 and asked == [("getRecentPrioritizationFees", [["A", "B"]])]


def test_the_mode_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv("KNOS_PRIORITY", raising=False)
    assert P.mode() is None
    for v, want in (("auto", "auto"), ("1500", 1500), ("off", None)):
        monkeypatch.setenv("KNOS_PRIORITY", v)
        assert P.mode() == want
    monkeypatch.setenv("KNOS_PRIORITY", "fast")
    with pytest.raises(ValueError):
        P.mode()


class L:
    url = "http://x"


def test_the_budget_is_the_simulated_units_with_headroom_and_the_price(monkeypatch):
    kp = Keypair()
    ix = Instruction(MEMO, b"hi", [AccountMeta(kp.pubkey(), True, True)])
    monkeypatch.setenv("KNOS_PRIORITY", "auto")
    monkeypatch.setattr(chain, "call", lambda url, m, p: {"value": {"err": None, "unitsConsumed": 40_000}} if m == "simulateTransaction"
                        else [{"prioritizationFee": 1234}])
    lim, price = P.budget(L(), [ix], kp)
    assert lim.program_id == CB and int.from_bytes(bytes(lim.data)[1:5], "little") == 46_300
    assert int.from_bytes(bytes(price.data)[1:9], "little") == 1234
    assert P.writable_of([ix], kp.pubkey()) == [str(kp.pubkey())]
    assert P.budget(L(), [set_compute_unit_limit(9), ix], kp) == []            # instructions that bring their own budget keep it
    monkeypatch.setattr(chain, "call", lambda url, m, p: {"value": {"err": {"x": 1}}} if m == "simulateTransaction" else [])
    (only,) = P.budget(L(), [ix], kp)                                           # no estimate, no fee: the most a transaction may use
    assert int.from_bytes(bytes(only.data)[1:5], "little") == P.MAX_UNITS
    monkeypatch.delenv("KNOS_PRIORITY")
    assert P.budget(L(), [ix], kp) == []


def test_the_websocket_url_of_a_cluster():
    assert P.ws_url("https://api.devnet.solana.com") == "wss://api.devnet.solana.com/"
    assert P.ws_url("http://127.0.0.1:8899") == "ws://127.0.0.1:8900/"


class FakeWS:
    def __init__(self, msgs):
        self.msgs, self.sent, self.closed = list(msgs), [], False

    def send(self, obj, opcode=1):
        self.sent.append(obj)

    def recv(self):
        return self.msgs.pop(0)

    def close(self):
        self.closed = True


def test_wait_ws_subscribes_and_returns_on_the_notification():
    ws = FakeWS([{"jsonrpc": "2.0", "result": 7, "id": 1},
                 {"method": "signatureNotification", "params": {"result": {"context": {"slot": 99}, "value": {"err": None}}, "subscription": 7}}])
    assert P.wait_ws("https://h", "SIG", 5, connect=lambda u: ws) == {"slot": 99, "err": None}
    assert ws.sent == [{"jsonrpc": "2.0", "id": 1, "method": "signatureSubscribe", "params": ["SIG", {"commitment": "confirmed"}]}] and ws.closed
    bad = FakeWS([{"method": "signatureNotification", "params": {"result": {"context": {"slot": 1}, "value": {"err": {"InstructionError": [0, "x"]}}}}}])
    with pytest.raises(ValueError, match="failed"):
        P.wait_ws("https://h", "SIG", 5, connect=lambda u: bad)
    with pytest.raises(ConnectionError):
        P.wait_ws("https://h", "SIG", 5, connect=lambda u: FakeWS([{"jsonrpc": "2.0", "id": 1, "error": {"code": -32602}}]))


def test_chain_wait_uses_the_websocket_and_falls_back_to_polling(monkeypatch):
    monkeypatch.setenv("KNOS_WS", "1")
    calls = []
    monkeypatch.setattr(chain, "call", lambda url, m, p: calls.append(m) or {"value": [None]})
    monkeypatch.setattr(P, "wait_ws", lambda url, sig, within, commitment: {"slot": 5, "err": None})
    assert chain.wait("https://h", "SIG")["slot"] == 5 and calls == ["getSignatureStatuses"]

    def down(*a, **k):
        raise ConnectionError("no websocket")
    monkeypatch.setattr(P, "wait_ws", down)
    statuses = iter([{"value": [None]}, {"value": [{"confirmationStatus": "confirmed", "err": None, "slot": 6}]}])
    monkeypatch.setattr(chain, "call", lambda url, m, p: next(statuses))
    assert chain.wait("https://h", "SIG", within=5)["slot"] == 6
