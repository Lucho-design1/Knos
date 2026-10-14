"""`knos record verify`: the file is held to its own hashes, to the Merkle roots anchored on chain, and to Sibyl's
memory. A fake chain stands in for devnet here (offline by default); tests/test_record_devnet.py reads the real one.
Sibyl is load-bearing: lines cut from the end of the file break no hash, and only Sibyl's journal says they existed."""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3

import pytest

from knos import record
from knos.proof import history
from knos.record import anchoring, journal

SIGNER = "8aukezen9sAALWShcZKK3hi8WawBi4vR6qmLf764PGBv"


class Chain:
    """A cluster that keeps each memo it is sent, and answers getTransaction for it."""

    def __init__(self):
        self.txs: dict[str, dict] = {}

    def send(self, memo: str) -> dict:
        sig = str(len(self.txs) + 1) * 88
        self.txs[sig] = {"found": True, "err": None, "memo": memo, "signers": [SIGNER], "slot": 100 + len(self.txs)}
        return {"tx": sig, "signer": SIGNER, "slot": self.txs[sig]["slot"]}

    def fetch(self, tx: str, cluster: str) -> dict:
        return self.txs.get(tx, {"found": False})


def fill(rec, n: int = 4) -> list[dict]:
    out = [record.claim("c1", {"title": "synthetic", "synthetic": True}, domain="ml", root=rec)]
    for i in range(n - 2):
        out.append(record.append("experiment", {"run": i, "value": 0.5 + i / 100, "synthetic": True}, claim="c1", root=rec))
    out.append(record.paper("p1", {"title": "t", "sha256": "e" * 64}, root=rec))
    return out


def rewrite(rec, lines: list[dict]) -> None:
    (rec / "journal.jsonl").write_text("".join(journal.canonical(e).decode() + "\n" for e in lines), encoding="utf-8")


@pytest.fixture()
def rec(tmp_path):
    return tmp_path / "rec"


def test_an_untouched_anchored_record_verifies_on_chain_and_against_sibyl(rec):
    chain = Chain()
    fill(rec)
    a1 = record.anchor(rec, send=chain.send)
    assert a1["kind"] == "anchor" and a1["payload"]["first"] == 0 and a1["payload"]["last"] == 3
    assert a1["payload"]["root"] == record.merkle_root([e["hash"] for e in record.entries(rec)[:4]])
    record.append("payout", {"amount": 5_000_000, "synthetic": True}, claim="c1", root=rec)
    a2 = record.anchor(rec, send=chain.send)
    assert (a2["payload"]["first"], a2["payload"]["last"]) == (4, 5)                    # the next batch starts after the last
    assert record.anchor(rec, send=chain.send)["payload"]["first"] == 6                 # an anchor line is anchored by the next
    rep = record.verify(rec, fetch=chain.fetch)
    assert rep["ok"], rep["problems"]
    assert [a["chain"] for a in rep["anchors"]] == ["ok", "ok", "ok"] and rep["unanchored"] == 1
    assert rep["sibyl"]["consulted"] and rep["sibyl"]["cold_events"] == 8 and rep["sibyl"]["warm_claims_ok"] == 1
    assert rep["sibyl"]["reference_papers_ok"] == 1


def test_nothing_pending_means_nothing_sent_and_a_dry_run_sends_nothing(rec):
    chain = Chain()
    assert record.anchor(rec, send=chain.send) is None
    fill(rec, 3)
    plan = record.anchor(rec, send=chain.send, dry_run=True)
    assert plan["memo"] == anchoring.memo_text(plan["root"], 0, 2, plan["head"]) and chain.txs == {}
    assert anchoring.parse_memo(plan["memo"]) == {k: plan[k] for k in ("root", "first", "last", "head")}


def test_an_edited_line_fails_its_hash_and_its_anchor(rec):
    chain = Chain()
    fill(rec)
    record.anchor(rec, send=chain.send)
    lines = record.entries(rec)
    lines[1]["payload"]["value"] = 0.99
    rewrite(rec, lines)
    rep = record.verify(rec, fetch=chain.fetch, use_sibyl=False)
    assert not rep["ok"] and any("does not hash to what it says" in p for p in rep["problems"])


def test_a_rewritten_history_with_fresh_hashes_is_caught_by_the_chain_and_by_sibyl(rec):
    """Someone rewrites a line and recomputes every hash and the anchor's root: the file is consistent with itself,
    but the memo on chain is the old root, and Sibyl's journal holds the old lines."""
    chain = Chain()
    fill(rec)
    record.anchor(rec, send=chain.send)
    lines = record.entries(rec)
    lines[1]["payload"]["value"] = 0.99
    prev = journal.GENESIS
    for e in lines[:4]:
        e["prev"] = prev
        e["hash"] = journal.line_hash(e)
        prev = e["hash"]
    p = lines[4]["payload"]
    p["root"] = record.merkle_root([e["hash"] for e in lines[:4]])
    p["head"] = lines[3]["hash"]
    p["memo"] = anchoring.memo_text(p["root"], 0, 3, p["head"])
    lines[4]["prev"] = lines[3]["hash"]
    lines[4]["hash"] = journal.line_hash(lines[4])
    rewrite(rec, lines)
    offline = record.verify(rec, offline=True, use_sibyl=False)
    assert offline["ok"]                                       # alone, a consistent forgery passes: that is why it is anchored
    on_chain = record.verify(rec, fetch=chain.fetch, use_sibyl=False)
    assert not on_chain["ok"] and on_chain["anchors"][0]["chain"] == "mismatch"
    with_sibyl = record.verify(rec, offline=True)
    assert not with_sibyl["ok"] and with_sibyl["sibyl"]["differs"] == [1, 2, 3, 4]


def test_lines_cut_from_the_end_break_no_hash_and_only_sibyl_remembers_them(rec):
    """Sibyl is load-bearing: cut unanchored lines from the end of the file and every hash still links. Held to
    Sibyl's journal the cut is caught; without consulting the memory, or with Sibyl's store deleted it is not."""
    fill(rec)
    record.append("refusal", {"passed": False, "reason": "a test file was edited", "synthetic": True}, claim="c1", root=rec)
    rewrite(rec, record.entries(rec)[:-1])
    assert record.verify(rec, offline=True, use_sibyl=False)["ok"]                          # no memory: nothing missed
    assert not record.verify(rec, offline=True, store=history.NullStore())["ok"]            # an empty memory vouches for nothing
    rep = record.verify(rec, offline=True)
    assert not rep["ok"] and rep["sibyl"]["missing_from_file"] == [4]
    for f in rec.glob("sibyl.db*"):
        f.unlink()
    assert record.verify(rec, offline=True)["ok"]                                           # Sibyl's store gone: nothing missed


def test_an_edited_sibyl_journal_disagrees_with_the_file(rec):
    fill(rec)
    with contextlib.closing(sqlite3.connect(rec / "sibyl.db")) as con:
        for old, new in (('"run":0', '"run":7'), ('"run": 0', '"run": 7')):
            con.execute("update journal_events set extra = replace(extra, ?, ?)", (old, new))
        con.commit()
    rep = record.verify(rec, offline=True)
    assert not rep["ok"] and rep["sibyl"]["differs"] == [1] and rep["sibyl"]["edited"] == [1]
    assert any("the memory was edited" in p for p in rep["problems"])


def test_an_anchor_whose_transaction_is_missing_failed_or_signed_by_another_is_refused(rec):
    chain = Chain()
    fill(rec)
    a = record.anchor(rec, send=chain.send)
    tx = a["payload"]["tx"]
    chain.txs[tx]["signers"] = ["11111111111111111111111111111111"]
    assert record.verify(rec, fetch=chain.fetch)["anchors"][0]["chain"] == "wrong signer"
    chain.txs[tx]["err"] = {"InstructionError": [0, "Custom"]}
    assert record.verify(rec, fetch=chain.fetch)["anchors"][0]["chain"] == "failed"
    del chain.txs[tx]
    rep = record.verify(rec, fetch=chain.fetch)
    assert not rep["ok"] and rep["anchors"][0]["chain"] == "not found"

    def down(tx, cluster):
        raise OSError("network is unreachable")
    rep = record.verify(rec, fetch=down)
    assert not rep["ok"] and rep["anchors"][0]["chain"].startswith("unreadable")       # never a pass by default
    assert record.verify(rec, fetch=down, offline=True)["ok"]


def test_an_anchor_on_mainnet_is_refused(rec, monkeypatch):
    chain = Chain()
    fill(rec, 2)
    monkeypatch.setenv("KNOS_CLUSTER", "mainnet")
    with pytest.raises(record.AnchorError, match="devnet"):
        record.anchor(rec, send=chain.send)


def test_a_secret_written_into_the_file_by_hand_is_reported(rec):
    fill(rec, 2)
    lines = record.entries(rec)
    lines[0]["payload"]["note"] = "ghp_" + "Z" * 36
    lines[0]["hash"] = journal.line_hash(lines[0])
    lines[1]["prev"] = lines[0]["hash"]
    lines[1]["hash"] = journal.line_hash(lines[1])
    rewrite(rec, lines)
    rep = record.verify(rec, offline=True, use_sibyl=False)
    assert not rep["ok"] and any("may not be in a public record" in p for p in rep["problems"])


def test_a_public_copy_without_sibyl_is_checked_by_hash_and_chain(rec, tmp_path):
    chain = Chain()
    fill(rec)
    record.anchor(rec, send=chain.send)
    copy = tmp_path / "public"
    copy.mkdir()
    shutil.copy(rec / "journal.jsonl", copy / "journal.jsonl")
    rep = record.verify(copy / "journal.jsonl", fetch=chain.fetch)
    assert rep["ok"] and rep["sibyl"] == {"consulted": False}
    from knos.record import verifier
    assert any("not consulted" in line for line in verifier.lines_of(rep)) and verifier.lines_of(rep)[-1] == "OK"
    proof = __import__("knos.record.cli", fromlist=["_prove"])._prove(copy, 2)
    assert proof["checks"] and proof["root"] == record.entries(copy)[4]["payload"]["root"]
    assert json.loads(json.dumps(proof))["size"] == 4


def test_a_rewritten_journal_re_anchored_with_another_wallet_is_refused_unless_that_key_is_trusted(rec, tmp_path, monkeypatch):
    """Review finding 18: the anchoring key is pinned outside the journal. Someone rewrites the whole history and
    anchors it with a wallet of their own: every hash, root and memo agrees, and the verifier still refuses it,
    because the key is not one it trusts. Told to trust that key (--signer, KNOS_RECORD_SIGNERS), it passes: the pin
    moves trust to a key, it cannot make the key's holder honest."""
    forger = "Forg3r1111111111111111111111111111111111111"
    chain = Chain()

    def forged_send(memo):
        sent = chain.send(memo)
        chain.txs[sent["tx"]]["signers"] = [forger]
        return {**sent, "signer": forger}

    forged = tmp_path / "forged"
    fill(forged)
    record.anchor(forged, send=forged_send)
    rep = record.verify(forged, fetch=chain.fetch, use_sibyl=False)
    assert not rep["ok"] and rep["anchors"][0]["chain"] == "ok" and rep["anchors"][0]["pinned"] is False
    assert any("not a pinned anchoring key" in p for p in rep["problems"])
    assert not record.verify(forged, offline=True, use_sibyl=False)["ok"]          # the pin holds offline too
    assert record.verify(forged, fetch=chain.fetch, use_sibyl=False, signers=[forger])["ok"]
    monkeypatch.setenv("KNOS_RECORD_SIGNERS", forger)
    assert record.verify(forged, fetch=chain.fetch, use_sibyl=False)["ok"]
    assert record.verify(forged, fetch=chain.fetch, use_sibyl=False, signers=[SIGNER])["ok"] is False
