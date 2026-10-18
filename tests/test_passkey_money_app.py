"""Knos's web app (apps/wanted) moving money only on passkey signatures, end to end inside LiteSVM: the deployed
LazorKit bytes and the knos_pay 0.3.34 test build. A buyer's passkey pre-orders, a maker's passkey claims the milestone
and sells the receivable, a lender's passkey advances and collects; the referees release; a missed deadline refunds.
The passkeys are software P-256 authenticators (tests/test_passkey_chain.py); the server never holds their keys.
Synthetic test units."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("solders.litesvm")

from solders.account import Account  # noqa: E402
from solders.keypair import Keypair  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

from test_passkey_chain import RP_ID, Passkey  # noqa: E402
from test_passkey_smart_chain import LAZOR_SO, World, tokens  # noqa: E402

from knos.settle.v2 import pay  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "wanted"))
from knos_wanted import auth, escrow, preorder, wallets  # noqa: E402

SLOT_HASHES = Pubkey.from_string("SysvarS1otHashes111111111111111111111111111")


class Led:
    """What the app needs of a cluster, over LiteSVM: reads, sends (legacy and v0), the slot, rent, and
    getProgramAccounts over every address a transaction named."""
    url = "http://127.0.0.1:8899"

    def __init__(self, c: World):
        self.c, self.n, self.seen, self.tables = c, 0, set(), 0

    def _named(self, ixs):
        for ix in ixs:
            self.seen.update(a.pubkey for a in ix.accounts)

    def account(self, addr):
        return self.c.data(addr)

    def send(self, ixs, payer, signers=None):
        self._named(ixs)
        if not self.c.send(list(ixs), payer, signers or (), mark=False):
            raise RuntimeError(f"transaction failed: {self.c.err}")
        self.n += 1
        return f"svm{self.n}"

    def send_v0(self, ixs, payer, tables):
        self._named(ixs)
        self.c.tables = tables
        if not self.c.send_v0(list(ixs), payer):
            raise RuntimeError(f"transaction failed: {self.c.err} {self.c.logs[-3:]}")
        self.n += 1
        self.size = self.c.size
        return f"svm{self.n}"

    def rent(self, size):
        return self.c.svm.minimum_balance_for_rent_exemption(size)

    def slot(self):
        return self.c.slot()

    def now(self):
        return self.c.now()

    def tick(self):
        k = self.c.svm.get_clock(); k.slot += 1; self.c.svm.set_clock(k)

    def recent_slot(self):
        top = self.c.slot()
        raw = (64).to_bytes(8, "little") + b"".join((top - i).to_bytes(8, "little") + bytes(32) for i in range(64))
        self.c.svm.set_account(SLOT_HASHES, Account(lamports=10 ** 9, data=raw + bytes(20_488 - len(raw)),
                                                    owner=Pubkey.from_string("Sysvar1111111111111111111111111111111111111"), executable=False))
        self.tables += 1
        return top - self.tables

    def program_accounts(self, program, size=None, memcmp=None):
        out = []
        for a in self.seen:
            acc = self.c.svm.get_account(a)
            if acc is None or acc.owner != program or not acc.lamports:
                continue
            d = bytes(acc.data)
            if all(d[o:o + len(b)] == b for o, b in (memcmp or {}).items()) and (size is None or len(d) == size):
                out.append((a, d))
        return out


class Person:
    def __init__(self, seed: int, label: str):
        self.p = Passkey(seed)
        self.cred_id = hashlib.sha256(b"cred %d" % seed).digest()
        self.sub = auth.identity(self.p.spki)
        auth._remember(self.sub, auth.b64u(self.cred_id), self.p.spki)
        self.user = {"sub": self.sub, "kind": "passkey", "label": label}

    def approve(self, led, step: dict) -> dict:
        """What the browser does: recompute the challenge from the parts, ask the passkey, post the answer; once more
        when the server says the authenticator answered otherwise than predicted."""
        for _ in range(3):
            parts = step["parts"]
            again = hashlib.sha256(bytes([parts["discriminator"]]) + bytes.fromhex(parts["auth_payload"]) + bytes.fromhex(parts["signed_payload"])
                                   + parts["slot"].to_bytes(8, "little") + bytes(Pubkey.from_string(parts["payer"]))
                                   + parts["counter"].to_bytes(4, "little") + bytes(Pubkey.from_string(parts["program"]))).digest()
            assert auth.b64u(again) == step["challenge"]
            ad, cdj, sig = self.p.get(auth.unb64u(step["challenge"]))
            got = wallets.sign(led, self.user, {"intent": step["intent"], "authenticatorData": auth.b64u(ad),
                                                "clientDataJSON": auth.b64u(cdj), "signature": auth.b64u(sig)})
            if not got.get("again"):
                return got
            step = got
        raise AssertionError("the passkey never matched")


@pytest.fixture
def app(monkeypatch, tmp_path):
    c = World()
    monkeypatch.setenv("KNOS_WANTED_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("KNOS_WANTED_RECORD", str(tmp_path / "record"))
    monkeypatch.setenv("KNOS_WANTED_DEVNET_KEYPAIR", json.dumps(list(bytes(c.payer))))     # the relayer: fees, rents, the faucet
    monkeypatch.delenv("KNOS_WANTED_RELAYER_KEYPAIR", raising=False)
    monkeypatch.setenv("KNOS_WANTED_MINT", str(c.usdc))
    monkeypatch.setenv("KNOS_WANTED_PROGRAM", str(pay.PAY_ID))
    monkeypatch.setenv("KNOS_WANTED_REFEREE_KEYS", json.dumps([list(bytes(Keypair())) for _ in range(3)]))
    wallets._pending.clear()
    return c, Led(c)


REPORT = {"hash": "c" * 64, "idea": "A repair kit for e-bike batteries", "label": "LIVE", "kind": "knos-demand-check",
          "decision": {"verdict": "OPEN", "target_units": 100, "reserve_units": 5, "plan": {"unit_price": 1}}}


class _Page:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return self.body


def test_a_buyers_passkey_preorders_a_makers_passkey_sells_the_receivable_and_the_lender_is_repaid_on_release(app):
    c, led = app
    buyer, maker, lender = Person(61, "buyer"), Person(62, "maker"), Person(63, "lender")
    w = wallets.public(led, wallets.holder(buyer.user), RP_ID)
    assert w["balance_units"] == 0 and "LazorKit" in w["kind"]
    f = wallets.faucet(led, wallets.holder(buyer.user), RP_ID)
    assert f["units"] == wallets.FAUCET_UNITS and "test money" in f["money"]
    with pytest.raises(ValueError, match="no maker"):
        wallets.prepare_preorder(led, buyer.user, REPORT, 6, RP_ID)
    wallets.claim_maker(led, maker.user, REPORT, RP_ID)
    with pytest.raises(wallets.NeedPasskey):                  # a guest has no wallet: nothing is bought for it
        wallets.prepare_preorder(led, {"sub": "guest:x", "kind": "guest", "label": "x"}, REPORT, 6, RP_ID)
    step = wallets.prepare_preorder(led, buyer.user, REPORT, 6, RP_ID)
    assert step["summary"]["amount_units"] == 6 and step["summary"]["from"] == w["vault"]
    with pytest.raises(wallets.NeedPasskey):                  # another person cannot answer this step
        maker.approve(led, step)
    rec = buyer.approve(led, step)
    assert rec["status"] == "locked" and rec["maker_wallet"] != w["vault"] and led.size <= preorder.TX_BUDGET
    order = Pubkey.from_string(rec["commitment"])
    assert c.order(order).amount == 6 * escrow.UNIT
    rvault = Pubkey.from_string(rec["maker_wallet"])
    # the lender quotes 90%; the maker's passkey sells; the lender's passkey pays the advance
    q = wallets.quote(led, lender.user, rec["commitment"], 9000, RP_ID)
    assert q["advance_units"] == 5.4 and q["fee_units"] == 0.6
    with pytest.raises(wallets.NeedPasskey):
        wallets.prepare_accept(led, lender.user, rec["commitment"], q["id"])
    sold = maker.approve(led, wallets.prepare_accept(led, maker.user, rec["commitment"], q["id"]))
    assert sold["factoring"]["status"] == "assigned"
    wallets.faucet(led, wallets.holder(lender.user), RP_ID)
    adv = lender.approve(led, wallets.prepare_advance(led, lender.user, rec["commitment"], RP_ID))
    assert adv["factoring"]["status"] == "advanced"
    maker_main = Pubkey.from_string(wallets.maker_of(REPORT["hash"])["main_vault"])
    assert tokens(c, pay.ata(maker_main, c.usdc)) == 5_400_000
    # the milestone is proven; two referees release to the receivable's wallet, which the lender owns now
    page = f"<html>shipped: {rec['claim_id']}</html>".encode()
    out = preorder.milestone(REPORT, rec["commitment"], "https://maker.example/proof", led=led,
                             opener=lambda req, timeout: _Page(page), resolve=lambda host: None)
    assert out["release"] == "released" and tokens(c, pay.ata(rvault, c.usdc)) == 6 * escrow.UNIT
    col = lender.approve(led, wallets.prepare_collect(led, lender.user, rec["commitment"], RP_ID))
    assert col["factoring"]["status"] == "repaid"
    me = wallets.addresses(wallets.holder(lender.user))["vault"]
    assert tokens(c, pay.ata(me, c.usdc)) == wallets.FAUCET_UNITS * escrow.UNIT - 5_400_000 + 6 * escrow.UNIT
    lst = wallets.receivables()
    assert lst[0]["face_units"] == 6 and lst[0]["factoring"]["status"] == "repaid"


def test_past_the_deadline_a_passkey_preorder_is_refunded_to_the_buyers_own_wallet(app):
    c, led = app
    buyer, maker = Person(64, "buyer"), Person(65, "maker")
    wallets.faucet(led, wallets.holder(buyer.user), RP_ID)
    wallets.claim_maker(led, maker.user, REPORT, RP_ID)
    rec = buyer.approve(led, wallets.prepare_preorder(led, buyer.user, REPORT, 5, RP_ID))
    tok = pay.ata(wallets.addresses(wallets.holder(buyer.user))["vault"], c.usdc)
    before = tokens(c, tok)
    o = c.order(Pubkey.from_string(rec["commitment"]))
    c.warp(31 * 86_400)
    out = preorder.refund(rec["commitment"], led=led)
    assert out["status"] in ("refunded", "closed") and tokens(c, tok) == before + o.amount + o.fee


def test_no_server_key_buys_any_more(app):
    with pytest.raises(wallets.NeedPasskey, match="passkey"):
        preorder.lock(REPORT, 5, "guest: x")
    assert not hasattr(escrow, "demo_preorder")
    assert LAZOR_SO.is_file()


def test_the_browser_recomputes_the_challenge_and_refuses_a_step_that_says_otherwise(app, tmp_path):
    """static/passkey_wallet.js in node: check() rebuilds the challenge from the parts and reads the FundOrderWallet
    amount out of the signed instructions; a summary that differs from what would be signed is refused."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    c, led = app
    buyer, maker = Person(66, "buyer"), Person(67, "maker")
    wallets.faucet(led, wallets.holder(buyer.user), RP_ID)
    wallets.claim_maker(led, maker.user, REPORT, RP_ID)
    step = wallets.prepare_preorder(led, buyer.user, REPORT, 7, RP_ID)
    js = Path(__file__).resolve().parents[1] / "apps" / "wanted" / "knos_wanted" / "static" / "passkey_wallet.js"
    lie = json.loads(json.dumps(step))
    lie["summary"]["amount_units"] = 1
    run = tmp_path / "run.js"
    run.write_text("global.window = {};\nrequire(%s);\n(async () => {\n  await window.KnosPasskey.check(%s);\n  let refused = false;\n"
                   "  try { await window.KnosPasskey.check(%s); } catch (e) { refused = true; }\n  console.log(refused ? 'OK' : 'ACCEPTED');\n"
                   "})().catch((e) => { console.log('FAIL ' + e.message); });\n" % (json.dumps(str(js)), json.dumps(step), json.dumps(lie)), encoding="utf-8")
    out = subprocess.run([node, str(run)], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "OK", out.stdout + out.stderr


def test_the_largest_passkey_preorder_fits_with_knos_margin():
    sizes = preorder.largest_preorder_txs()
    assert sizes["passkey_preorder"] <= preorder.TX_BUDGET == 1182, sizes
