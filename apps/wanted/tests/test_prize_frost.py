"""A demo round's prize is funded by the round's SPONSOR and, with the FROST referee group configured, released only by
2 of the 3 referee hosts after they fetch and re-check its published evidence (knos_wanted.tasks, knos_wanted.referee).
The chain is replaced by recorders here (the on-chain path of a group signature is tests/test_threshold_frost.py)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos_wanted import escrow, preorder, referee, tasks

GK = str(Keypair().pubkey())
WALLET = str(Keypair().pubkey())


class Led:
    def account(self, a):
        return b"x"                    # every token account exists

    def send(self, ixs, payer, extra=None):
        raise AssertionError("nothing is sent before the commitment in this test")


def _wire(monkeypatch, frost=True):
    from knos.ideas import commit as C
    seen = {}
    monkeypatch.setattr(escrow, "ledger", lambda: Led())
    sponsor = Keypair()
    monkeypatch.setattr(escrow, "demo_key", lambda: sponsor)
    monkeypatch.setattr(escrow, "mint", lambda led, create=True: Pubkey.default())
    monkeypatch.setattr(escrow, "_token_units", lambda led, tok: 10 ** 12)
    monkeypatch.setattr(preorder, "ready", lambda: (True, ""))
    monkeypatch.setattr(preorder, "panel", lambda: (1, [GK]) if frost else (2, ["a", "b", "c"]))

    def commit(claim, **kw):
        seen["commit"] = {"claim": claim, **kw}
        return {"claim": claim, "commitment_hash": "ab" * 32, "panel": {"m": kw["panel"][0], "keys": kw["panel"][1]},
                "orders": {"stage1": {"order": str(Keypair().pubkey()), "signature": "LOCK"}}}
    monkeypatch.setattr(C, "commit", commit)

    def start(rec, url, led, kind="preorder"):
        seen["start"] = {"rec": rec, "url": url, "kind": kind}
        return {"session": "f" * 32, "github": referee.GITHUB_HOST, "needs": "2 of 3"}
    monkeypatch.setattr(referee, "start", start)
    return seen, sponsor


def test_a_scored_attempts_prize_is_funded_by_the_sponsor_and_waits_for_the_frost_group(monkeypatch):
    seen, sponsor = _wire(monkeypatch)
    got = tasks._prize("knos-demo-1", {"n": 1, "sha256": "00" * 32, "decision": "scored"}, "ada", WALLET, "https://knos.example")
    assert got["paid"] is False and got["status"] == "signing" and got["session"] == "f" * 32
    assert got["funded_by"] == tasks.SPONSOR and "sponsor" in got["label"] and "buyer" not in got["label"]
    assert seen["commit"]["funder"] is sponsor and seen["commit"]["panel"] == (1, [GK])            # the group key, 1 of 1
    assert seen["start"]["kind"] == "prize" and seen["start"]["url"] == "https://knos.example/api/prize/evidence?id=" + "ab" * 8
    page = tasks.prize_evidence("ab" * 8)
    assert page and seen["commit"]["claim"]["id"].encode() in page                       # what each host requires
    assert json.loads(page)["verdict"]["decision"] == "scored"
    assert tasks.load_prize(got["order"])["status"] == "locked"
    assert tasks.prize_evidence("../../etc") is None and tasks.prize_evidence("cd" * 8) is None


def test_the_second_share_releases_the_prize_and_records_it(monkeypatch):
    from knos.ideas import commit as C
    from knos.threshold import check
    seen, _ = _wire(monkeypatch)
    got = tasks._prize("knos-demo-1", {"n": 2, "decision": "scored"}, "ada", WALLET)
    monkeypatch.setattr(C, "_order", lambda doc, st, led: (None, SimpleNamespace(stamp=7)))
    monkeypatch.setattr(check, "verdict_record", lambda *a: {"verdict": "PASS", "args": len(a)})
    monkeypatch.setattr(preorder, "relayer", lambda: Keypair())
    sent = {}

    def release(doc, st, recs, payer, led):
        sent["recs"] = recs
        return {"status": "released", "sent": [{"signature": "REL"}]}
    monkeypatch.setattr(C, "release", release)
    s = {"id": "f" * 32, "meta": {"order": got["order"], "kind": "prize", "evidence": {"evidence_hash": "e"}}, "digest": "00" * 32,
         "signature": "11" * 64, "group_key": GK, "signers": [1, 3]}
    out = referee._released(s)
    assert out == {"status": "released", "signatures": ["REL"]} and sent["recs"] == [{"verdict": "PASS", "args": 7}]
    rec = tasks.load_prize(got["order"])
    assert rec["status"] == "released" and rec["signatures"]["referee_group_pass"] == "REL" and rec["referee_session"]["signers"] == [1, 3]


def test_without_the_frost_group_the_server_keys_sign_at_once(monkeypatch):
    from knos.ideas import commit as C
    seen, _ = _wire(monkeypatch, frost=False)
    keys = [Keypair() for _ in range(3)]
    monkeypatch.setattr(preorder, "referees", lambda: keys)
    monkeypatch.setattr(C, "sign", lambda doc, st, r, led, passed, review: {"by": str(r.pubkey())})
    monkeypatch.setattr(C, "release", lambda doc, st, recs, payer, led: {"status": "released", "sent": [{"signature": "R1"}]})
    monkeypatch.setattr(preorder, "relayer", lambda: Keypair())
    got = tasks._prize("knos-demo-1", {"n": 3}, "ada", WALLET)
    assert got["paid"] is True and got["release"] == ["R1"] and "start" not in seen and got["funded_by"] == tasks.SPONSOR
