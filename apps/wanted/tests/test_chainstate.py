"""knos_wanted.chainstate in LiteSVM with the SPL Record program as deployed on devnet (tests/thirdparty): a project is
written to its record account, grows into a new one (the old one closed), and is read back from the account bytes;
restore keeps the newest record of each project. M1's live half is test_project_survives_redeploy (scripts)."""
from pathlib import Path

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from test_chainx import Ledger

from knos_wanted import chainstate

SO = Path(__file__).resolve().parents[3] / "tests" / "thirdparty" / "spl_record_devnet_recr1L3.so"


@pytest.fixture
def led():
    led = Ledger()
    led.svm.add_program(Pubkey.from_string(chainstate.RECORD), SO.read_bytes())
    return led


def test_encode_decode_round_trip():
    obj = {"id": "p" * 16, "title": "Recovery shoe", "versions": [{"criteria_hash": "c" * 64}]}
    got = chainstate.decode(chainstate.encode("projects", "p" * 16, obj, at_ns=7))
    assert got == ("projects", "p" * 16, 7, obj) and chainstate.decode(b"other data") is None


def test_a_project_is_written_grows_and_is_read_back(led, monkeypatch):
    chainstate._index.clear()
    payer = Keypair()
    led.svm.airdrop(payer.pubkey(), 10_000_000_000)
    pid = "a" * 16
    small = {"id": pid, "title": "Small", "versions": [{"criteria_hash": "c" * 64}]}
    first = chainstate.write("projects", pid, small, led=led, payer=payer)
    raw = bytes(led.svm.get_account(Pubkey.from_string(first)).data)
    assert raw[0] == 1 and raw[1:33] == bytes(payer.pubkey())                       # version 1, our relayer the authority
    assert chainstate.decode(raw[chainstate.HEADER:])[3] == small
    assert chainstate.write("projects", pid, {**small, "title": "Same size"}, led=led, payer=payer) == first   # written in place
    big = {**small, "history": [{"what": f"step {i} " + "x" * 40} for i in range(400)]}  # beyond the first account's room
    second = chainstate.write("projects", pid, big, led=led, payer=payer)
    gone = led.svm.get_account(Pubkey.from_string(first))
    assert second != first and (gone is None or gone.lamports == 0)                  # the old record closed
    raw = bytes(led.svm.get_account(Pubkey.from_string(second)).data)
    assert chainstate.decode(raw[chainstate.HEADER:])[3] == big
    # restore: the newest record of each project wins, and is saved again
    older = ("old", 10, ("projects", pid, 1, small))
    newer = ("new", 10, ("projects", pid, 2, big))
    monkeypatch.setattr(chainstate, "records", lambda url, authority: [older, newer])
    saved = {}
    assert chainstate.restore(lambda k, n, o: saved.__setitem__((k, n), o), led=led, payer=payer) == 1 and saved[("projects", pid)] == big


def test_off_unless_the_hosted_app_turns_it_on(monkeypatch):
    monkeypatch.delenv("KNOS_STATE_ON_CHAIN", raising=False)
    chainstate.queue_save("projects", "b" * 16, {"id": "b" * 16})
    assert chainstate._q.empty()
