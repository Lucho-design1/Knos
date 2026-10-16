"""Pre-order with any Solana wallet: a Solana Action (Blink) and the factoring of a receivable.

    GET  /actions.json                                   the Actions rules file (which paths are actions)
    GET  /api/actions/preorder?report=<hash>             the action: title, description, buttons (Solana Actions spec)
    POST /api/actions/preorder?report=<hash>&units=N     {"account": "<wallet>"} -> {"type": "transaction", "transaction": b64}

The transaction is the same PANEL order a signed-in pre-order locks (knos.ideas.commit), with the wallet as the funder:
it creates the wallet's token account for this app's devnet TEST mint, tops it up with test units (the server signs as
the test mint's authority), and funds the escrow order. The wallet signs and sends it; the server never holds the
wallet's key. Devnet only, test money.

Factoring (POST /api/factor): knos_pay has an Assign instruction (0x18: an order's payment goes to another wallet),
but the program accepts it only from a payee with a BOUND wallet (a Bind proved by GitHub or ORCID). A payee named only by
a wallet address is refused with E_PAYEE (88). The server simulates the Assign on devnet and reports that result; when
the program refuses, the factoring offer is a labelled SIMULATION recorded off-program, never a claim that it ran.
"""
from __future__ import annotations

import base64
import os

from . import escrow, preorder

DEVNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, Content-Encoding, Accept-Encoding",
        "Access-Control-Expose-Headers": "X-Action-Version, X-Blockchain-Ids", "X-Action-Version": "2.4", "X-Blockchain-Ids": DEVNET}
RULES = {"rules": [{"pathPattern": "/api/actions/**", "apiPath": "/api/actions/**"}]}


class _Capture:
    """A ledger that records what knos.ideas.commit would send, and sends nothing."""

    def __init__(self, led):
        self.led, self.sent = led, []
        self.url = led.url

    def account(self, addr):
        return self.led.account(addr)

    def send(self, ixs, payer, signers=()):
        self.sent.append(list(ixs))
        return None


class _Wallet:
    def __init__(self, pk):
        self._pk = pk

    def pubkey(self):
        return self._pk


def action(report: dict, base: str) -> dict:
    d = report.get("decision") or {}
    plan = d.get("plan") or {}
    if d.get("verdict") != "OPEN":
        return {"type": "action", "icon": base + "/static/icon.svg", "title": "Knos pre-order", "label": "Closed", "disabled": True,
                "description": "Pre-orders open only on a report whose decision is OPEN.", "error": {"message": "not open"}}
    href = f"/api/actions/preorder?report={report['hash']}"
    who = plan.get("who") or {}
    return {"type": "action", "icon": base + "/static/icon.svg", "title": f"Pre-order: {report['idea'][:80]}",
            "description": (f"For {(who.get('age') or '').replace('_', ' ')} {who.get('gender') or ''}; launching in "
                            f"{', '.join(plan.get('where') or []) or 'its first cities'}. {plan.get('unit_price')} test units per unit "
                            f"({plan.get('tier')} tier, set by Qloo). Held in escrow on Solana devnet; paid to the maker only on proof. Test money."),
            "label": "Pre-order",
            "links": {"actions": [{"type": "transaction", "label": f"Pre-order 5 units ({5 * int(plan.get('unit_price') or 1)} test units)",
                                   "href": href + "&units=5"},
                                  {"type": "transaction", "label": "Pre-order", "href": href + "&units={units}",
                                   "parameters": [{"name": "units", "label": "Units (5 or more)", "type": "number", "required": True}]}]}}


def preorder_tx(report: dict, account: str, units: int, label: str = "wallet") -> dict:
    """The unsigned (server-partially-signed) devnet transaction for a wallet's pre-order, and the pending commitment."""
    from solders.hash import Hash
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    from knos import chain, ideas
    from knos.ideas import commit as C
    from knos.settle.v2 import pay
    d = report.get("decision") or {}
    if d.get("verdict") != "OPEN":
        raise ValueError("pre-orders open only on a report whose decision is OPEN")
    price = int((d.get("plan") or {}).get("unit_price") or preorder.PRICE)
    if isinstance(units, bool) or not isinstance(units, int) or not 5 <= units <= min(1000, d["target_units"]):
        raise ValueError(f"units: 5 to {min(1000, d['target_units'])}")
    try:
        wallet = Pubkey.from_string(account)
    except ValueError:
        raise ValueError("account: a Solana wallet address") from None
    preorder._need()
    led = escrow.ledger()
    authority, refs = escrow.demo_key(), preorder.referees()
    mint = escrow.mint(led, create=False)
    maker = (os.environ.get("KNOS_WANTED_MAKER_WALLET") or "").strip()
    n = len(preorder.of_report(report["hash"])) + 1
    claim = ideas.claim(f"Pre-order {n} for: {report['idea']} (Knos demand report {report['hash'][:16]})", field_name=preorder.FIELD,
                        kind="person", by={"app": "knos demand check", "report": report["hash"], "buyer": label[:80]})
    tok = pay.ata(wallet, mint)
    cap = _Capture(led)
    doc = C.commit(claim, units=units, price=price, payee=C.parse_payee(maker), funder=_Wallet(wallet), funder_token=tok, mint=mint,
                   led=cap, stages=[("referee_pass", 10_000)], stage_work_s=[30 * 86_400],
                   panel=(2, [str(r.pubkey()) for r in refs]), program=preorder.program(), demand_hash=report["hash"], unlisted_panel=True)
    amount = units * price * escrow.UNIT
    setup = [pay.create_ata_ix(authority.pubkey(), w, mint) for w in (pay.FEE_OWNER, Pubkey.from_string(maker)) if led.account(pay.ata(w, mint)) is None]
    if setup:                      # the fee owner's and the maker's token accounts: made once by the server, not in the wallet's transaction
        led.send(setup, authority)
    ixs = [pay.create_ata_ix(wallet, wallet, mint)] if led.account(tok) is None else []
    ixs.append(escrow._mint_to_ix(mint, tok, authority.pubkey(), -(-(amount + pay.order_fee(amount)) // escrow.UNIT)))
    ixs += [ix for batch in cap.sent for ix in batch if ix.program_id == preorder.program()]
    bh = Hash.from_string(chain.call(led.url, "getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, wallet, bh))
    tx.partial_sign([authority], bh)
    raw = bytes(tx)
    if len(raw) > preorder.TX_BUDGET:
        raise ValueError(f"the pre-order transaction is {len(raw)} bytes, above Knos's budget of {preorder.TX_BUDGET} (Solana's limit is 1,232)")
    st = doc["orders"]["stage1"]
    rec = {"order": st["order"], "report": report["hash"], "idea": report["idea"], "claim_id": claim["id"], "units": units, "unit_price": price,
           "buyer": f"wallet {account} ({label[:60]}), test money", "maker_wallet": maker, "status": "pending", "deadline_days": 30,
           "doc": doc, "made": doc["made"], "signatures": {}, "via": "Solana Action (Blink)"}
    preorder._save(rec)
    return {"type": "transaction", "transaction": base64.b64encode(raw).decode(), "bytes": len(raw), "commitment": st["order"],
            "message": f"Locks {units * price} test units in escrow on devnet for {units} units; paid to the maker only on proof."}


def refresh(rec: dict, led=None) -> dict:
    """A pending wallet pre-order becomes locked once its order account exists on chain."""
    if rec.get("status") != "pending":
        return rec
    from solders.pubkey import Pubkey
    led = led or escrow.ledger()
    if led.account(Pubkey.from_string(rec["order"])) is not None:
        rec["status"] = "locked"
        from . import company
        rec["record"] = company.record_lock(rec["report"], rec["order"], rec["units"], None)
        preorder._save(rec)
    return rec


# ---- factoring -------------------------------------------------------------------------------------------------------
def factor(rec: dict, discount_bps: int = 500, led=None) -> dict:
    """Offer the maker cash now for the escrowed receivable. Simulates knos_pay's Assign on devnet; when the program
    refuses (a wallet-only payee has no Bind), records the offer as a labelled off-program SIMULATION."""
    from solders.hash import Hash
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    from knos import chain
    from knos.settle.v2 import pay
    if not 0 <= int(discount_bps) <= 3000:
        raise ValueError("discount_bps: 0 to 3,000")
    led = led or escrow.ledger()
    face = rec["units"] * int(rec.get("unit_price") or preorder.PRICE)
    advance = face * (10_000 - int(discount_bps)) / 10_000
    funder = escrow.demo_key().pubkey()
    maker = Pubkey.from_string(rec["maker_wallet"])
    ix = pay.assign_ix(maker, Pubkey.from_string(rec["order"]), rec["doc"]["payee"]["payee_id"], funder, program=preorder.program())
    tx = Transaction.new_unsigned(Message.new_with_blockhash([ix], maker, Hash.default()))
    sim = chain.call(led.url, "simulateTransaction", [base64.b64encode(bytes(tx)).decode(),
                                                      {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True}], timeout=20)
    v = sim.get("value") or {}
    err = v.get("err")
    on_chain = err is None
    code = (((err or {}).get("InstructionError") or [None, {}])[1] or {}).get("Custom") if isinstance(err, dict) else None
    out = {"commitment": rec["order"], "face_value": face, "discount_bps": int(discount_bps), "advance": advance, "funder": str(funder),
           "assign_instruction": "knos_pay Assign (0x18)", "assign_simulation": {"err": err, "custom_code": code,
                                                                                  "meaning": pay.ERRORS.get(code) if hasattr(pay, "ERRORS") and code else None}}
    if on_chain:
        out.update(status="ready", note="the program accepts this Assign: the maker signs the returned transaction",
                   transaction=base64.b64encode(bytes(tx)).decode())
    else:
        out.update(status="SIMULATED (off-program)",
                   note="knos_pay refused the Assign in simulation (a payee named only by a wallet has no Bind; E_PAYEE 88). "
                        "This offer is recorded off-program as a SIMULATION: no assignment exists on chain, and the release still pays the maker.")
    rec["factoring"] = out
    preorder._save(rec)
    return out
