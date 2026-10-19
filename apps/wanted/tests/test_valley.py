"""Projects (knos_wanted.valley): templates, tranches released on an independent check, parallel attempts, referral
payees, the deadline sweeper (refund + reopen), AMC allowances and the megafund pool. No network: a fake ledger."""
import base64
import json
import struct
import types

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos_wanted import valley

MAKER = {"sub": "pk:maker", "kind": "passkey", "label": "maker"}
CHECKER = {"sub": "pk:checker", "kind": "passkey", "label": "checker"}
OWNER = {"sub": "pk:owner", "kind": "passkey", "label": "owner"}


class Led:
    url = "https://api.devnet.solana.com"

    def __init__(self):
        self.accounts, self.sent, self.t = {}, [], 1_000

    def account(self, a):
        return self.accounts.get(str(a))

    def send(self, ixs, payer, signers=()):
        self.sent.append(ixs)
        return "5" * 88

    def now(self):
        return self.t


@pytest.fixture
def money(monkeypatch):
    from knos import chain

    from knos_wanted import escrow, preorder
    refs = [Keypair() for _ in range(3)]
    auth = Keypair()
    mint = Keypair().pubkey()
    monkeypatch.setattr(preorder, "_need", lambda: None)
    monkeypatch.setattr(preorder, "referees", lambda: refs)
    monkeypatch.setattr(preorder, "relayer", lambda: auth)
    monkeypatch.setattr(escrow, "demo_key", lambda: auth)
    monkeypatch.setattr(escrow, "mint", lambda led=None, create=True: mint)
    monkeypatch.setattr(chain, "call", lambda url, m, p, timeout=20: {"value": {"blockhash": "11111111111111111111111111111111"}})
    led = Led()
    return types.SimpleNamespace(led=led, refs=refs, auth=auth, mint=mint)


def test_templates_cover_the_five_and_the_regulatory_sets():
    t = valley.templates()
    keys = {x["key"] for x in t["templates"]}
    assert keys == {"ai_model_eval", "hardware_prototype", "internal_tool", "paper_to_pilot", "vendor_deliverable"}
    for x in t["templates"]:
        assert sum(m["share_bps"] for m in x["milestones"]) == 10_000
    reg = t["regulatory"]
    assert {s["key"] for s in reg["sets"]} == {"iso13485", "mdr"}
    assert "CC BY-NC-SA 4.0" in reg["licence"] and "OpenRegulatory" in reg["attribution"]
    for s in reg["sets"]:
        for m in s["milestones"]:
            assert m["template"].startswith("https://github.com/openregulatory/templates/blob/62d2facc")


def test_project_with_regulatory_milestones_and_bounds():
    p = valley.create_project(OWNER, "hardware_prototype", "Sweat glucose watch", regulatory=["iso13485", "mdr"])
    kinds = [m["kind"] for m in p["milestones"]]
    assert kinds[:3] == ["build"] * 3 and kinds.count("regulatory") == 14
    reg = [m for m in p["milestones"] if m["kind"] == "regulatory"]
    assert all(m["attribution"] and m["template"] for m in reg)
    assert p["milestones"][1]["route"]["kind"] == "electronics"
    with pytest.raises(valley.Refused):
        valley.create_project(OWNER, "nope", "x y z")
    with pytest.raises(valley.Refused):
        valley.create_project(OWNER, "internal_tool", "tool", deadline_s=10)
    sb = valley.create_project(OWNER, "internal_tool", "Sandbox tool", deadline_s=86_400)
    assert sb["sandbox"] is True and all(m["deadline_s"] == 86_400 for m in sb["milestones"])


def _funded(money, deadline_s=120, ref=None):
    p = valley.create_project(OWNER, "paper_to_pilot", "MOF water bottle", deadline_s=deadline_s)
    funder = Keypair().pubkey()
    tx = valley.fund_tx(p["id"], "reproduce", 10, str(funder), ref=ref, led=money.led)
    assert base64.b64decode(tx["transaction"]) and tx["bytes"] <= 1182
    o = valley._load("orders", tx["order"])
    assert o["status"] == "pending" and o["doc"]["orders"]["stage1"]["work_s"] == deadline_s
    with pytest.raises(valley.Refused):
        valley.confirm(tx["order"], led=money.led)             # not on chain yet
    money.led.accounts[tx["order"]] = b"order"
    got = valley.confirm(tx["order"], "4" * 88, led=money.led)
    assert got["status"] == "locked"
    return p, tx, funder


def test_fund_confirm_and_grant(money):
    p, tx, _ = _funded(money)
    assert valley.public_project(valley.project(p["id"]))["milestones"][0]["status"] == "funded"
    with pytest.raises(valley.Refused):
        valley.fund_tx(p["id"], "reproduce", 10, str(Keypair().pubkey()), kind="grant", grant={"agency": "NIH"}, led=money.led)
    g = valley.fund_tx(p["id"], "reproduce", 10, str(Keypair().pubkey()), kind="grant",
                       grant={"agency": "NIH", "id": "R01-EXAMPLE", "url": "https://reporter.nih.gov"}, led=money.led)
    assert valley._load("orders", g["order"])["grant"]["agency"] == "NIH"


def test_independent_check_rules_and_parallel_attempts(money, monkeypatch):
    p, tx, _ = _funded(money)
    cid = valley._load("orders", tx["order"])["claim_id"]
    page = f"<html>{cid} result</html>".encode()
    a = valley.claim(p["id"], "reproduce", MAKER, str(Keypair().pubkey()))
    b = valley.claim(p["id"], "reproduce", {"sub": "pk:m2", "label": "maker 2"}, str(Keypair().pubkey()))
    assert a["id"] != b["id"]
    with pytest.raises(valley.Refused):
        valley.claim(p["id"], "reproduce", MAKER, str(Keypair().pubkey()))            # one attempt per maker
    fetch = lambda url: page  # noqa: E731
    with pytest.raises(valley.Refused):
        valley.post(p["id"], "reproduce", a["id"], CHECKER, "https://lab.example.org/r", "result", fetch=fetch)   # not the maker
    valley.post(p["id"], "reproduce", a["id"], MAKER, "https://lab.example.org/r", "result", fetch=fetch)
    with pytest.raises(valley.Refused):
        valley.post(p["id"], "reproduce", a["id"], MAKER, "https://other.example.net/c", "check", fetch=fetch)   # the maker
    with pytest.raises(valley.Refused):
        valley.post(p["id"], "reproduce", a["id"], CHECKER, "https://www.example.org/c", "check", fetch=fetch)   # same site
    from knos_wanted import preorder
    with pytest.raises(preorder.NotVerified):
        valley.post(p["id"], "reproduce", a["id"], CHECKER, "https://repl.example.net/c", "check", fetch=lambda u: b"no id")
    seen = {}
    monkeypatch.setattr(valley, "release", lambda pid, key, att, led=None: seen.update(att=att) or {"released": []})
    got = valley.post(p["id"], "reproduce", a["id"], CHECKER, "https://repl.example.net/c", "check", fetch=fetch)
    assert got["verdict"]["pass"] and "att" not in seen              # human-verified: the challenge window runs first
    assert valley.release_due(now=got["verdict"]["ends_s"] - 1) == []
    valley.release_due(now=got["verdict"]["ends_s"])
    assert seen["att"] == a["id"]


def test_release_pays_maker_and_referrer_share(money):
    ref = valley.make_referral(OWNER, str(Keypair().pubkey()), "p=" + "a" * 16)
    assert ref["link"].startswith("/r/") and ref["share_bps"] == 500
    p, tx, _ = _funded(money, ref=ref["code"])
    cid = valley._load("orders", tx["order"])["claim_id"]
    wallet = str(Keypair().pubkey())
    a = valley.claim(p["id"], "reproduce", MAKER, wallet)
    page = cid.encode()
    valley.post(p["id"], "reproduce", a["id"], MAKER, "https://a.example.org/r", "result", fetch=lambda u: page)
    pr = valley.project(p["id"])
    att = pr["milestones"][0]["attempts"][0]
    att["check"], att["check_sub"], att["status"] = {"url": "https://b.example.net/c", "sha256": "0" * 64, "host": "b.example.net"}, "pk:c", "checked"
    valley._save("projects", p["id"], pr)
    signed = []

    def sign(doc, stage, r, led, passed, review):
        from knos.ideas import commit as C
        signed.append(C.payees_of(doc["payee"]))
        assert json.loads(review.read_text())["rule"].startswith("result + independent check")
        return {"sig": 1}

    got = valley.release(p["id"], "reproduce", a["id"], led=money.led, sign=sign,
                         release_fn=lambda doc, st, recs, rel, led: {"status": "released", "sent": [{"signature": "s1"}, {"signature": "s2"}]})
    assert got["released"][0]["status"] == "released" and got["milestone"] == "released"
    payees = signed[0]
    assert [b for _, b, _ in payees] == [9500, 500] and str(payees[0][2]) == wallet
    assert str(payees[1][2]) == valley.load_referral(ref["code"])["wallet"]


def test_large_release_goes_as_v1(monkeypatch):
    from knos import chain
    sent = []

    class L:
        url = "https://api.devnet.solana.com"

        def send(self, ixs, payer, signers=None, v1=False):
            sent.append(v1)
            return "sig"
    monkeypatch.setattr(chain, "tx_size", lambda ixs, payer, v1: 1928 if len(ixs) > 1 else 900)
    led = valley._V1Ledger(L())
    kp = Keypair()
    led.send([1], kp)
    led.send([1, 2], kp)
    assert sent == [False, True] and led.v1_sent == ["sig"]


def test_payee_split_is_checked():
    from knos.ideas import commit as C
    w = str(Keypair().pubkey())
    with pytest.raises(Exception):
        C.payees_of({"payee_id": 1, "wallet": w, "split": [{"payee_id": 1, "bps": 9000, "wallet": w}]})


def test_sweep_refunds_and_reopens(money, monkeypatch):
    from knos.settle.v2 import pay
    p, tx, _ = _funded(money)
    a = valley.claim(p["id"], "reproduce", MAKER, str(Keypair().pubkey()))
    monkeypatch.setattr(pay, "read_order", lambda data: types.SimpleNamespace(pay_until=500))
    refunded = []
    got = valley.sweep(led=money.led, refund_fn=lambda doc, st, recs, rel, led: refunded.append(doc) or {"status": "refunded", "sent": [{"signature": "r1"}]})
    assert refunded and got["swept"][0]["reopened"]["reopened"]
    m = valley.public_project(valley.project(p["id"]))["milestones"][0]
    assert m["status"] == "reopened" and m["attempts"][0]["status"] == "missed the deadline" and m["excluded_makers"] == 1
    with pytest.raises(valley.Refused):
        valley.claim(p["id"], "reproduce", MAKER, str(Keypair().pubkey()))
    valley.claim(p["id"], "reproduce", {"sub": "pk:new", "label": "new maker"}, str(Keypair().pubkey()))
    assert valley._load("orders", tx["order"])["status"] == "refunded"
    assert a


def test_amc_allowance_and_collect(money):
    p = valley.create_project(OWNER, "vendor_deliverable", "Lab notebook export")
    buyer = Keypair().pubkey()
    out = valley.amc_tx(p["id"], "delivered", 7, str(buyer), led=money.led)
    from solders.transaction import Transaction
    tx = Transaction.from_bytes(base64.b64decode(out["transaction"]))
    data = [bytes(i.data) for i in tx.message.instructions]
    assert bytes([4]) + struct.pack("<Q", 7_000_000) in data           # SPL Approve to the relayer
    from knos.settle.v2 import pay
    tok = str(pay.ata(buyer, money.mint))
    acc = bytearray(165)
    acc[64:72] = struct.pack("<Q", 7_000_000)
    acc[72:76] = b"\x01\x00\x00\x00"
    acc[76:108] = bytes(money.auth.pubkey())
    acc[121:129] = struct.pack("<Q", 7_000_000)
    money.led.accounts[tok] = bytes(acc)
    assert valley.amc_confirm(out["amc"], led=money.led)["status"] == "approved"
    got = valley.collect_amc(p["id"], "delivered", str(Keypair().pubkey()), led=money.led)
    assert got[0]["status"] == "collected"
    sent = money.led.sent[-1][0]
    assert bytes(sent.data) == bytes([3]) + struct.pack("<Q", 7_000_000)


def test_pool_spreads_over_milestones(money):
    a = valley.create_project(OWNER, "internal_tool", "Tool A")
    b = valley.create_project(OWNER, "ai_model_eval", "Eval B")
    out = valley.pool_txs([{"project": a["id"], "milestone": "spec", "weight": 1}, {"project": b["id"], "milestone": "result", "weight": 3}],
                          40, str(Keypair().pubkey()), led=money.led)
    assert len(out["transactions"]) == 2 and out["units"] == 40
    kinds = {valley._load("orders", t["order"])["kind"] for t in out["transactions"]}
    assert kinds == {"pool"}
    with pytest.raises(valley.Refused):
        valley.pool_txs([{"project": a["id"], "milestone": "spec"}], 10, str(Keypair().pubkey()), led=money.led)


def test_route_quotes_are_labelled():
    p = valley.create_project(OWNER, "paper_to_pilot", "Protein binder")
    r = valley.route(valley._milestone(valley.project(p["id"]), "reproduce"))
    assert r["kind"] == "proteins" and r["capacity"][0]["adapter"] == "adaptyv"
    q = r["capacity"][0]["quote"]
    assert "error" in q or q["mode"] in ("fixture", "live")
    assert "commitments cover" in r["rule"]
    assert Pubkey  # imported for the fixtures


def test_a_frost_milestone_waits_for_two_of_three_hosts_then_pays_maker_and_referrer(money, monkeypatch):
    """With the FROST referee group configured, a project order pins the group key (1 of 1) and no server-held key
    signs: the attempt's review is published, a session opens per order, and the second share releases it."""
    from knos.ideas import commit as C
    from knos.threshold import check

    from knos_wanted import preorder, referee
    gk = str(Keypair().pubkey())
    monkeypatch.setattr(preorder, "panel", lambda: (1, [gk]))
    monkeypatch.setattr(preorder, "referees", lambda: (_ for _ in ()).throw(AssertionError("no server-held key signs")))
    monkeypatch.setattr(referee, "enabled", lambda: True)
    starts = []
    monkeypatch.setattr(referee, "start", lambda rec, url, led, kind="preorder": starts.append((rec, url, kind)) or
                        {"session": "e" * 32, "github": referee.GITHUB_HOST, "needs": "2 of 3"})
    ref = valley.make_referral(OWNER, str(Keypair().pubkey()), "p=" + "b" * 16)
    p, tx, _ = _funded(money, ref=ref["code"])
    o = valley._load("orders", tx["order"])
    assert o["doc"]["panel"] == {"m": 1, "keys": [gk], "unlisted": True, "label": o["doc"]["panel"]["label"]}
    wallet = str(Keypair().pubkey())
    with pytest.raises(valley.Refused):
        valley.claim(p["id"], "reproduce", {"sub": "pk:x", "label": "x"}, gk)        # the group key is never a payee
    a = valley.claim(p["id"], "reproduce", MAKER, wallet)
    valley.post(p["id"], "reproduce", a["id"], MAKER, "https://a.example.org/r", "result", fetch=lambda u: o["claim_id"].encode())
    pr = valley.project(p["id"])
    att = pr["milestones"][0]["attempts"][0]
    att["check"], att["check_sub"], att["status"] = {"url": "https://b.example.net/c", "sha256": "0" * 64, "host": "b.example.net"}, "pk:c", "checked"
    valley._save("projects", p["id"], pr)
    got = valley.release(p["id"], "reproduce", a["id"], led=money.led, base="https://knos.example")
    assert got["milestone"] == "signing" and got["released"][0]["status"] == "signing"
    rec, url, kind = starts[0]
    assert kind == "project" and url.startswith("https://knos.example/api/project/evidence?id=")
    page = valley.project_evidence(url.rsplit("=", 1)[1])
    assert o["claim_id"].encode() in page and json.loads(page)["rule"].startswith("result + independent check")
    assert [b for _, b, _ in C.payees_of(rec["doc"]["payee"])] == [9500, 500]           # maker + referrer, in the signed digest
    assert valley.project(p["id"])["milestones"][0]["status"] != "released"
    # a retry while the session is open does not open a second one
    monkeypatch.setattr(referee, "coordinator", lambda: types.SimpleNamespace(get=lambda sid: {"state": "round1"}))
    valley.release(p["id"], "reproduce", a["id"], led=money.led)
    assert len(starts) == 1
    # the second share: the group signature is the verdict; the order is released and the milestone settles
    monkeypatch.setattr(C, "_order", lambda doc, st, led: (None, types.SimpleNamespace(stamp=3)))
    monkeypatch.setattr(check, "verdict_record", lambda *a: {"verdict": "PASS", "group": a[5]})
    monkeypatch.setattr(valley, "_ledger", lambda led=None: money.led)
    monkeypatch.setattr(C, "release", lambda doc, st, recs, payer, led: {"status": "released", "sent": [{"signature": "G1"}]}
                        if recs == [{"verdict": "PASS", "group": gk}] else {"status": "locked", "sent": []})
    s = {"id": "e" * 32, "meta": {"order": tx["order"], "kind": "project", "evidence": {"evidence_hash": "h"}}, "digest": "00" * 32,
         "signature": "22" * 64, "group_key": gk, "signers": [1, 2]}
    out = referee._released(s)
    assert out["status"] == "released" and out["milestone"] == "released"
    done = valley._load("orders", tx["order"])
    assert done["signatures"]["referee_group_pass"] == "G1" and done["paid_to"]["maker"] == wallet and done["referee_session"]["signers"] == [1, 2]
    assert valley.project(p["id"])["milestones"][0]["status"] == "released"


def test_ready_gate_freeze_change_request_and_kill_fee(money):
    vague = {"milestones": [{"key": "app", "name": "Make the app faster", "target": "better"}]}
    p = valley.create_project(OWNER, "custom", "A vague app", brief=vague)
    assert p["ready"]["label"] == "Not ready" and "app.verifier" in p["ready"]["missing"]
    with pytest.raises(valley.Refused, match="Not ready to fund"):
        valley.fund_tx(p["id"], "app", 10, str(Keypair().pubkey()), led=money.led)
    clear = {"milestones": [{"key": "app", "name": "Checkout p95 latency", "target": "p95 under 300 ms on test_checkout_latency",
                             "verifier": {"kind": "machine", "check": "ci / test_checkout_latency"}, "deadline_s": 120}], "kill_fee_bps": 1500}
    p = valley.edit_brief(p["id"], OWNER, clear)
    assert p["ready"]["ready"] and p["kill_fee_bps"] == 1500
    tx = valley.fund_tx(p["id"], "app", 10, str(Keypair().pubkey()), led=money.led)
    o = valley._load("orders", tx["order"])
    assert o["criteria_hash"] == p["ready"]["criteria_hash"] and o["criteria_hash"] in o["doc"]["claim"]["statement"]
    money.led.accounts[tx["order"]] = b"order"
    valley.confirm(tx["order"], "4" * 88, led=money.led)
    with pytest.raises(valley.Refused, match="change request"):
        valley.edit_brief(p["id"], OWNER, clear)
    a = valley.claim(p["id"], "app", MAKER, str(Keypair().pubkey()))
    new = {**clear, "milestones": [{**clear["milestones"][0], "target": "p95 under 250 ms on test_checkout_latency"}]}
    cr = valley.change_request(p["id"], OWNER, new, "tighter target")
    with pytest.raises(valley.Refused):
        valley.decide_change(p["id"], OWNER, cr["id"], True)                     # the buyer cannot accept its own change
    got = valley.decide_change(p["id"], MAKER, cr["id"], True)
    assert got["status"] == "accepted" and got["project"]["frozen"]["criteria_hash"] == cr["criteria_hash"] != cr["from_hash"]
    assert a["status"] == "working"
