"""Pre-orders on an OPEN demand report, paid to the maker only on proof: Knos's staged escrow (knos.ideas.commit).

One pre-order = one commitment with ONE stage, "milestone" (oracle referee_pass), locked on the knos_pay 0.3.34 TEST
program on devnet as a PANEL order: 2 of 3 referee keys release it to the maker's wallet; past its deadline anyone
refunds it to the buyer. Who is who on this server (all devnet TEST keys, no real money):
  buyer     KNOS_WANTED_DEVNET_KEYPAIR: the app's demo devnet wallet, acting for the signed-in user ("demo buyer, test money")
  maker     the payee: the maker's devnet wallet (the request's maker_wallet, else KNOS_WANTED_MAKER_WALLET)
  referees  KNOS_WANTED_REFEREE_KEYS: a JSON list of 3 secret keys (base58 strings or byte arrays) the SERVER holds.
            One server holding all three is NOT an independent panel; the commitment says UNLISTED PANEL (the keys are
            not in Knos's referee registry, config/referees.yaml).
  relayer   KNOS_WANTED_RELAYER_KEYPAIR (default: the buyer) sends the verdicts.
The milestone is verified by code before any referee signs: the maker's evidence URL is fetched over https (public
addresses only, no redirects, size and time limits) and must contain the commitment's claim id. Verified: 2 referees
sign PASS over that page (its sha256 is the evidence) and the server releases. Not verified: nothing is signed, the
money stays locked, and after the deadline it is refunded. The maker is paid only once the report's reserve is met.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import company, escrow

PROGRAM_034_TEST = "FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4"   # knos_pay 0.3.34 TEST build on devnet
FIELD = "Business, Management and Accounting"
PRICE = 1                       # test units per pre-ordered unit
MAX_EVIDENCE = 512_000
EVIDENCE_TIMEOUT_S = 10
_lock = threading.Lock()


class Unavailable(escrow.EscrowUnavailable):
    pass


class NotVerified(ValueError):
    pass


def _kp(v):
    from solders.keypair import Keypair
    if isinstance(v, list):
        return Keypair.from_bytes(bytes(v))
    if isinstance(v, str) and v.strip().startswith("["):
        return Keypair.from_bytes(bytes(json.loads(v)))
    if isinstance(v, str) and Path(v).expanduser().is_file():
        return _kp(json.loads(Path(v).expanduser().read_text(encoding="utf-8")))
    return Keypair.from_base58_string(str(v).strip())


def referees() -> list:
    raw = os.environ.get("KNOS_WANTED_REFEREE_KEYS", "")
    if not raw:
        raise Unavailable("escrow unavailable on this server (no referee keys: KNOS_WANTED_REFEREE_KEYS)")
    try:
        got = json.loads(raw) if raw.strip().startswith("[") else json.loads(Path(raw).expanduser().read_text(encoding="utf-8"))
        keys = [_kp(k) for k in got]
    except Exception:  # noqa: BLE001 - never echo the value
        raise Unavailable("escrow unavailable on this server (KNOS_WANTED_REFEREE_KEYS is not a JSON list of 3 secret keys)") from None
    if len(keys) != 3 or len({str(k.pubkey()) for k in keys}) != 3:
        raise Unavailable("escrow unavailable on this server (KNOS_WANTED_REFEREE_KEYS: 3 distinct keys)")
    return keys


def ready() -> tuple[bool, str]:
    if not os.environ.get("KNOS_WANTED_REFEREE_KEYS") or not os.environ.get("KNOS_WANTED_DEVNET_KEYPAIR"):
        return False, "escrow unavailable on this server"
    try:
        escrow.knos()
        from knos.ideas import commit  # noqa: F401
    except Exception as why:  # noqa: BLE001
        return False, f"escrow unavailable on this server ({type(why).__name__})"
    return True, "ok"


def _need() -> None:
    ok, why = ready()
    if not ok:
        raise Unavailable(why)


def program():
    from solders.pubkey import Pubkey
    return Pubkey.from_string(os.environ.get("KNOS_WANTED_PROGRAM") or PROGRAM_034_TEST)


def relayer():
    v = os.environ.get("KNOS_WANTED_RELAYER_KEYPAIR")
    return _kp(v) if v else escrow.demo_key()


def _dir() -> Path:
    d = escrow._state_dir() / "commitments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(rec: dict) -> None:
    f = _dir() / f"{rec['order']}.commit"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def load(order: str) -> dict:
    if not isinstance(order, str) or not order.isalnum() or not 32 <= len(order) <= 44:
        raise ValueError("commitment: the order address a pre-order returned")
    f = _dir() / f"{order}.commit"
    if not f.exists():
        raise ValueError("unknown commitment on this server")
    return json.loads(f.read_text(encoding="utf-8"))


def of_report(report_hash: str) -> list[dict]:
    out = []
    for f in sorted(_dir().glob("*.commit")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if r.get("report") == report_hash:
            out.append({k: r[k] for k in ("order", "units", "buyer", "status", "claim_id", "made") if k in r})
    return out


def fee_line(units: int | None = None) -> dict:
    """What Knos takes, from config/fees.yaml: the payout fee, held with the money and taken only at release."""
    try:
        from knos.money import fees_config
        cfg = fees_config.load()
        f = cfg.doc["fees"]
        bps = int(f["payout"]["rate_bps"])
        out = {"rate_bps": bps, "percent": bps / 100, "floor": f["payout"].get("floor_usd"), "status": f["payout"]["status"],
               "funding_fee_bps": int(f["funding"]["rate_bps"]), "graduation": {"rate_bps": int(f["graduation"]["rate_bps"]),
               "status": f["graduation"]["status"], "collected": f["graduation"].get("collected")},
               "text": f"Knos takes {bps / 100:g}% (at least {f['payout'].get('floor_usd')} test units) only on money released on proof; "
                       "a refund costs the buyer nothing", "source": "config/fees.yaml (fees.payout, fees.funding)"}
        if units:
            out["on_this_preorder"] = cfg.fee("payout", int(units) * escrow.UNIT * PRICE) / escrow.UNIT
        return out
    except Exception as why:  # noqa: BLE001
        return {"text": "fees: knos is not installed on this server", "why": type(why).__name__}


# ---- lock ------------------------------------------------------------------------------------------------------------
def lock(report: dict, units: int, buyer_label: str, maker_wallet: str | None = None, days: int | None = None, led=None) -> dict:
    """Lock `units` test units for the maker of an OPEN report, judged by the 2-of-3 panel. Returns the commitment record.
    The decision is READ from the Knos Record (Sibyl) first: a report Sibyl does not hold as OPEN, with the same target
    and reserve, locks nothing."""
    d = report.get("decision") or {}
    if d.get("verdict") != "OPEN" or report.get("label", "").startswith("NO QLOO"):
        raise ValueError("pre-orders open only on a report whose decision is OPEN on live Qloo evidence")
    held = company.record_state(report.get("hash", ""))
    if held.get("verdict") != "OPEN" or not held.get("live") or (held.get("target_units"), held.get("reserve_units")) != (d.get("target_units"), d.get("reserve_units")):
        raise company.NotInRecord("the Knos Record (Sibyl) does not hold this report as OPEN with this target and reserve")
    _need()
    from solders.pubkey import Pubkey

    from knos import ideas
    from knos.ideas import commit as C
    from knos.settle.v2 import pay
    if isinstance(units, bool) or not isinstance(units, int) or not 5 <= units <= min(1000, d["target_units"]):
        raise ValueError(f"units: 5 to {min(1000, d['target_units'])} (the report's target)")
    maker = (maker_wallet or os.environ.get("KNOS_WANTED_MAKER_WALLET") or "").strip()
    try:
        Pubkey.from_string(maker)
    except ValueError:
        raise ValueError("maker_wallet: the maker's devnet wallet address (or set KNOS_WANTED_MAKER_WALLET)") from None
    days = days or int(os.environ.get("KNOS_WANTED_MILESTONE_DAYS", "30"))
    led = led or escrow.ledger()
    buyer, refs, prog = escrow.demo_key(), referees(), program()
    mint = escrow.mint(led)
    with _lock:
        n = len(of_report(report["hash"])) + 1
        claim = ideas.claim(f"Pre-order {n} for: {report['idea']} (Knos demand report {report['hash'][:16]})", field_name=FIELD,
                            kind="person", by={"app": "knos demand check", "report": report["hash"], "buyer": buyer_label[:80]})
        tok = pay.ata(buyer.pubkey(), mint)
        pre = [pay.create_ata_ix(buyer.pubkey(), w, mint) for w in (buyer.pubkey(), Pubkey.from_string(maker))
               if led.account(pay.ata(w, mint)) is None]
        if pre:
            led.send(pre, buyer)
        need = units * PRICE * escrow.UNIT + pay.order_fee(units * PRICE * escrow.UNIT)
        have = escrow._token_units(led, tok)
        minted = None
        if have < need:
            minted = led.send([escrow._mint_to_ix(mint, tok, buyer.pubkey(), -(-(need - have) // escrow.UNIT))], buyer)
        doc = C.commit(claim, units=units, price=PRICE, payee=C.parse_payee(maker), funder=buyer, funder_token=tok, mint=mint, led=led,
                       stages=[("referee_pass", 10_000)], stage_work_s=[days * 86_400],
                       panel=(2, [str(r.pubkey()) for r in refs]), program=prog, demand_hash=report["hash"], unlisted_panel=True)
        st = doc["orders"]["stage1"]
        rec = {"order": st["order"], "report": report["hash"], "idea": report["idea"], "claim_id": claim["id"], "units": units,
               "buyer": f"demo buyer, test money (for {buyer_label[:80]})", "maker_wallet": maker, "status": "locked",
               "deadline_days": days, "doc": doc, "made": doc["made"],
               "signatures": {"mint_to_buyer": minted, "lock": st["signature"]}}
        rec["record"] = company.record_lock(report["hash"], st["order"], units, st["signature"])
        _save(rec)
    return public(rec)


def public(rec: dict) -> dict:
    sigs = {k: v for k, v in rec.get("signatures", {}).items() if v}
    return {"commitment": rec["order"], "claim_id": rec["claim_id"], "report": rec["report"], "units": rec["units"],
            "buyer": rec["buyer"], "maker_wallet": rec["maker_wallet"], "status": rec["status"], "milestone": "stage1 (referee_pass)",
            "panel": {"m": 2, "of": 3, "keys": rec["doc"]["panel"]["keys"], "label": rec["doc"]["panel"]["label"] or "UNLISTED PANEL",
                      "note": "the three referee keys are held by this one server: not an independent panel"},
            "program": rec["doc"]["program"], "mint": rec["doc"]["mint"], "deadline_days": rec["deadline_days"],
            "signatures": sigs, "explorer": {k: escrow.explorer(v) for k, v in sigs.items() if isinstance(v, str)},
            "order_explorer": escrow.explorer(rec["order"], "address"), "evidence": rec.get("evidence"),
            "how_to_prove": f"publish a public https page that contains {rec['claim_id']} and post its URL as the milestone evidence",
            "money": "test units of this app's own devnet test mint: test money, 0 revenue", "fees": fee_line(rec["units"]),
            "record": rec.get("record"), "release_record": rec.get("release_record")}


# ---- milestone evidence ----------------------------------------------------------------------------------------------
def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise NotVerified(f"{host}: does not resolve") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise NotVerified(f"{host}: resolves to a private or reserved address; evidence must be on the public internet")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        raise NotVerified("the evidence URL redirects; post the final https URL")


def fetch_evidence(url: str, opener=None, resolve=_public_host) -> bytes:
    u = urllib.parse.urlparse(str(url or "").strip())
    if u.scheme != "https" or not u.hostname or u.username or u.password or (u.port not in (None, 443)):
        raise NotVerified("evidence_url: a public https URL (port 443, no credentials)")
    if len(url) > 2000:
        raise NotVerified("evidence_url: at most 2,000 characters")
    resolve(u.hostname)
    op = opener or urllib.request.build_opener(_NoRedirect).open
    req = urllib.request.Request(url, headers={"User-Agent": "knos-demand-check milestone verifier", "Accept": "text/html,text/plain,application/json"})
    try:
        with op(req, timeout=EVIDENCE_TIMEOUT_S) as r:
            body = r.read(MAX_EVIDENCE + 1)
    except NotVerified:
        raise
    except urllib.error.HTTPError as e:
        raise NotVerified(f"the evidence URL answered HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise NotVerified(f"the evidence URL could not be read ({type(e).__name__})") from None
    if len(body) > MAX_EVIDENCE:
        raise NotVerified(f"the evidence page is larger than {MAX_EVIDENCE:,} bytes")
    return body


def verify(rec: dict, url: str, opener=None, resolve=_public_host) -> tuple[dict, bytes]:
    body = fetch_evidence(url, opener, resolve)
    if rec["claim_id"].encode() not in body:
        raise NotVerified(f"the evidence page does not contain the commitment's claim id {rec['claim_id']}")
    return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "contains_claim_id": True}, body


def reserve_status(report: dict, held: dict | None = None) -> dict:
    """Units pre-ordered vs the reserve, as the Knos Record (Sibyl) holds them; this server's files when Sibyl has none."""
    if held is None:
        try:
            held = company.record_state(report["hash"])
        except company.NotInRecord:
            held = None
    if held is not None:
        pre = held.get("preorders") or {}
        return {"pre_ordered_units": pre.get("units", 0), "reserve_units": held.get("reserve_units") or 0,
                "met": pre.get("units", 0) >= (held.get("reserve_units") or 0), "source": "Knos Record (Sibyl)"}
    locked = sum(r["units"] for r in of_report(report["hash"]) if r.get("status") in ("locked", "released"))
    need = (report.get("decision") or {}).get("reserve_units") or 0
    return {"pre_ordered_units": locked, "reserve_units": need, "met": locked >= need, "source": "this server's files (not in the Record)"}


def record_gate(rec: dict) -> dict:
    """Before a release: the Record (Sibyl) must hold this pre-order and must not hold it as released already."""
    held = company.record_state(rec["report"])
    if rec["order"] in (held.get("released") or []):
        raise company.NotInRecord("refused: the Knos Record (Sibyl) marks this commitment released")
    if rec["order"] not in ((held.get("preorders") or {}).get("list") or []):
        raise company.NotInRecord("the Knos Record (Sibyl) holds no pre-order for this commitment")
    return held


def milestone(report: dict, order: str, url: str, led=None, opener=None, resolve=_public_host) -> dict:
    """Verify the maker's evidence; when verified and the reserve is met, 2 referees sign PASS and the server releases."""
    rec = load(order)
    held = record_gate(rec)              # Sibyl first: its record alone refuses a second release, before files or chain
    if rec["status"] != "locked":
        raise ValueError(f"this commitment is already {rec['status']}")
    _need()
    from knos.ideas import commit as C
    res = reserve_status(report, held)
    if not res["met"]:
        raise ValueError(f"reserve not met: {res['pre_ordered_units']} of {res['reserve_units']} units pre-ordered; the maker is paid once it is")
    ev, body = verify(rec, url, opener, resolve)
    led = led or escrow.ledger()
    doc = rec["doc"]
    review = _dir() / f"{order}.evidence"           # the page the referees sign over: its sha256 is the verdict's evidence
    review.write_bytes(body)
    refs = referees()
    with _lock:
        recs = [C.sign(doc, "stage1", r, led, passed=True, review=review) for r in refs[:2]]
        got = C.release(doc, "stage1", recs, relayer(), led)
        rec["status"] = got["status"] if got["status"] in ("released", "refunded") else "locked"
        rec["evidence"] = ev
        for i, s in enumerate(got["sent"], 1):
            rec["signatures"][f"referee_{i}_pass"] = s["signature"]
        if rec["status"] == "released":
            rec["release_record"] = company.record_release(rec["report"], order, [s["signature"] for s in got["sent"]], ev["sha256"])
        _save(rec)
    return {**public(rec), "verified": ev, "release": got["status"], "reserve": res}


def refund(order: str, led=None) -> dict:
    """Past the deadline, the locked pre-order goes back to the buyer (knos.ideas.commit.refund, no verdicts)."""
    _need()
    from knos.ideas import commit as C
    rec = load(order)
    led = led or escrow.ledger()
    with _lock:
        got = C.refund(rec["doc"], "stage1", [], relayer(), led)
        rec["status"] = got["status"]
        if got["sent"]:
            rec["signatures"]["refund"] = got["sent"][0]["signature"]
        _save(rec)
    return public(rec)


# ---- preflight: is the money path really working on this server? ----------------------------------------------------
PREFLIGHT_TTL_S = 600
_pre: dict = {"at": 0.0, "ok": False, "why": "not checked yet"}
_pre_lock = threading.Lock()


def _simulate(led, ixs, payer, signers) -> dict:
    """simulateTransaction (nothing is sent): the cluster runs the transaction against current state."""
    import base64

    from solders.hash import Hash
    from solders.message import Message
    from solders.transaction import Transaction

    from knos import chain
    tx = Transaction(signers, Message.new_with_blockhash(ixs, payer, Hash.default()), Hash.default())
    got = chain.call(led.url, "simulateTransaction", [base64.b64encode(bytes(tx)).decode(),
                                                      {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True,
                                                       "commitment": "confirmed"}], timeout=20)
    return got.get("value") or {}


def preflight(led=None) -> tuple[bool, str]:
    """Build the transaction a 5-unit pre-order sends (test mint top-up, the stage's PANEL order with the server's 3
    referee keys) and SIMULATE it on devnet with the demo buyer. Every import, key, config file and the buyer's SOL are
    exercised; nothing is sent. (False, why) on any failure."""
    ok, why = ready()
    if not ok:
        return False, why
    try:
        from solders.keypair import Keypair
        from solders.system_program import CreateAccountParams, create_account

        from knos import chain, ideas
        from knos.ideas import wanted as W
        from knos.settle.v2 import pay
        led = led or escrow.ledger()
        buyer, refs, prog = escrow.demo_key(), referees(), program()
        ixs, signers = [], [buyer]
        try:
            mint = escrow.mint(led, create=False)
        except escrow.EscrowUnavailable:            # no test mint yet: the first pre-order makes one; simulate that too
            m = Keypair()
            rent = chain.call(led.url, "getMinimumBalanceForRentExemption", [escrow.MINT_LEN])
            from solders.instruction import AccountMeta, Instruction
            ixs += [create_account(CreateAccountParams(from_pubkey=buyer.pubkey(), to_pubkey=m.pubkey(), lamports=rent,
                                                       space=escrow.MINT_LEN, owner=pay.TOKEN)),
                    Instruction(pay.TOKEN, bytes([20, 6]) + bytes(buyer.pubkey()) + b"\x00", [AccountMeta(m.pubkey(), False, True)])]
            mint, signers = m.pubkey(), [buyer, m]
        tok = pay.ata(buyer.pubkey(), mint)
        ixs += [pay.create_ata_ix(buyer.pubkey(), w, mint) for w in (buyer.pubkey(), pay.FEE_OWNER) if led.account(pay.ata(w, mint)) is None]
        ixs.append(escrow._mint_to_ix(mint, tok, buyer.pubkey(), 6))
        claim = ideas.claim("Knos demand check preflight: a 5-unit pre-order, simulated only", field_name=FIELD, kind="agent")
        p = W.plan(claim, units=5, price=PRICE, stages=[("referee_pass", 10_000)], stage_work_s=[30 * 86_400])
        ixs.append(W.fund_panel_ix(p, "stage1", buyer.pubkey(), tok, mint, 2, [bytes(r.pubkey()) for r in refs], program=prog,
                                   unlisted_panel=True))
        v = _simulate(led, ixs, buyer.pubkey(), signers)
    except Exception as e:  # noqa: BLE001 - the reason is shown on /api/status (no secrets: names and types only)
        return False, f"pre-order preflight failed: {type(e).__name__}: {str(e)[:160]}"
    if v.get("err") is not None:
        logs = [x for x in (v.get("logs") or []) if "rror" in x][-1:]
        return False, f"pre-order preflight: devnet simulation failed ({v.get('err')}{'; ' + logs[0][:160] if logs else ''})"
    return True, f"ok: a pre-order transaction simulated on devnet ({v.get('unitsConsumed', '?')} compute units)"


def preflight_status(force: bool = False, led=None) -> dict:
    with _pre_lock:
        if force or time.time() - _pre["at"] > PREFLIGHT_TTL_S:
            ok, why = preflight(led)
            _pre.update(at=time.time(), ok=ok, why=why)
        return {"available": _pre["ok"], "why": _pre["why"], "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_pre["at"])),
                "preflight": "simulateTransaction of a 5-unit pre-order on devnet, every 10 minutes"}
