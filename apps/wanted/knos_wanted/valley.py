"""Projects: the valley of death's risks built into the money (devnet test units, Solana devnet only).

A PROJECT is one product's road, made from a milestone template (AI model eval, hardware prototype, internal tool,
paper to pilot, vendor deliverable) plus, for a regulated product, the regulatory milestones of OpenRegulatory's open
templates (ISO 13485, EU MDR). Every milestone is a TRANCHE: its own knos_pay panel order, funded by anyone, and

  released   only when the maker's result AND an independent check of it are both posted: two public https pages that
             contain the milestone's claim id, from two different sites, by two different signed-in people (the checker
             is never the maker). The server fetches both, the 2-of-3 panel signs PASS over the pair, the program pays.
  parallel   several makers may attempt one milestone at once (up to MAX_ATTEMPTS); the first independently checked
             result is paid, so one failed attempt does not kill the product. Code-scored milestones also open a
             knos.game round (the Contribute tab).
  refunded   past its deadline, by the sweeper thread in this server (sweep, every SWEEP_S): knos_pay RefundOrder sends
  + reopened the money back to the funder, the milestone REOPENS to other makers (the maker who missed it is excluded),
             and its funders are listed to re-fund it in one tap.

Money in, all real devnet transactions the funder's own wallet signs (the server only co-signs the test-unit top-up,
as the test mint's authority): a funder's escrow, a GRANT (the same order, labelled with the grant's agency and id),
a POOL (one funder spreads one amount over many milestones of many projects: the megafund), and an AMC COMMITMENT
(advance-market-commitment style: the buyer's wallet approves a token allowance to the relayer; nothing moves until the
milestone verifies, then the relayer pays the maker from it; the buyer can revoke the allowance until then, and the
page says so). A referral link names a referrer wallet: on release, the referrer's share is a second knos_pay payee.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import threading
import time
from pathlib import Path

from . import company, escrow

MAX_ATTEMPTS = 3
REFERRAL_BPS = 500                    # the referrer's share of a release paid through its link (5%)
SWEEP_S = int(os.environ.get("KNOS_VALLEY_SWEEP_S", "60"))
MIN_DEADLINE_S = 60                   # knos_pay's shortest stage deadline (pay.MIN_WORK)


def _token():
    from knos.settle.v2 import pay
    return pay.TOKEN                  # the SPL Token program (the test mint is a classic SPL mint)
_lock = threading.RLock()


class Refused(ValueError):
    pass


# ---- storage ---------------------------------------------------------------------------------------------------------
def _dir(kind: str) -> Path:
    d = escrow._state_dir() / "valley" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(kind: str, key: str, obj: dict) -> dict:
    f = _dir(kind) / f"{key}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, f)
    return obj


def _load(kind: str, key: str) -> dict:
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", key):
        raise Refused(f"{kind}: unknown id")
    f = _dir(kind) / f"{key}.json"
    if not f.exists():
        raise Refused(f"{kind}: unknown id")
    return json.loads(f.read_text(encoding="utf-8"))


def _all(kind: str) -> list[dict]:
    out = []
    for f in sorted(_dir(kind).glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _id(*parts) -> str:
    return hashlib.sha256(json.dumps([*parts, time.time_ns(), os.urandom(8).hex()]).encode()).hexdigest()[:16]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _journal(kind: str, data: dict) -> dict:
    """The decision log (Sibyl COLD, through the Knos Record): every funding, claim, release, refund and reopen."""
    rec = company._record()
    if rec is None:
        return {"recorded": False, "why": "the knos package is not installed"}
    return company._safe(lambda: {"recorded": True, "seq": rec.append(kind, {**data, "cluster": "devnet", "money": "devnet test units"},
                                                                     claim=company.claim_id(data.get("project", "0" * 64)),
                                                                     domain=company.DOMAIN, root=company.root())["seq"]})


# ---- templates -------------------------------------------------------------------------------------------------------
def catalogue() -> dict:
    import copy

    from .templates_data import CATALOGUE
    return copy.deepcopy(CATALOGUE)


def templates() -> dict:
    c = catalogue()
    reg = c["regulatory"]
    return {"templates": [{"key": k, "name": t["name"], "for": t["for"], "route": t["route"],
                           "milestones": [{"key": m["key"], "name": m["name"], "days": m["days"], "share_bps": m["bps"]} for m in t["milestones"]]}
                          for k, t in c["templates"].items()],
            "regulatory": {"sets": [{"key": k, "name": s["name"], "milestones": [{"key": m["key"], "name": m["name"],
                                                                                  "template": f"{reg['source']}/blob/{reg['commit']}/{m['path']}"}
                                                                                 for m in s["milestones"]]}
                                    for k, s in reg["sets"].items()],
                           "attribution": reg["attribution"], "licence": reg["licence"], "source": reg["source"], "commit": reg["commit"]},
            "rules": {"release": "the maker's result + an independent check (another person, another site), both containing the claim id",
                      "parallel_attempts": MAX_ATTEMPTS, "missed_deadline": "refunded to the funder and reopened to other makers by this server's sweeper",
                      "referral_share_bps": REFERRAL_BPS}}


# ---- projects --------------------------------------------------------------------------------------------------------
def _user_key(user: dict) -> str:
    return str(user.get("sub") or f"{user.get('kind')}:{user.get('label')}")[:120]


def create_project(user: dict, template: str, title: str, regulatory: list[str] | None = None, report: str | None = None,
                   team: str | None = None, deadline_s: int | None = None) -> dict:
    """A project from a template (+ regulatory sets). `deadline_s` shortens every milestone's deadline (the one-day
    sandbox, and the reopen demonstration): at least knos_pay's minimum of 60 s."""
    c = catalogue()
    if template not in c["templates"]:
        raise Refused(f"template: one of {', '.join(c['templates'])}")
    title = (title or "").strip()[:120]
    if len(title) < 3:
        raise Refused("title: what the project makes (3 to 120 characters)")
    regulatory = [r for r in (regulatory or []) if r]
    for r in regulatory:
        if r not in c["regulatory"]["sets"]:
            raise Refused(f"regulatory: any of {', '.join(c['regulatory']['sets'])}")
    if deadline_s is not None and (isinstance(deadline_s, bool) or not isinstance(deadline_s, int) or not MIN_DEADLINE_S <= deadline_s <= 90 * 86_400):
        raise Refused("deadline_s: 60 to 7,776,000 seconds")
    t = c["templates"][template]
    ms = []
    for m in t["milestones"]:
        ms.append({"key": m["key"], "name": m["name"], "kind": "build", "share_bps": m["bps"], "route": m.get("route") or t["route"],
                   "game": bool(m.get("game")), "deadline_s": deadline_s or m["days"] * 86_400})
    reg = c["regulatory"]
    for r in regulatory:
        for m in reg["sets"][r]["milestones"]:
            ms.append({"key": f"{r}_{m['key']}", "name": m["name"], "kind": "regulatory", "share_bps": 0, "route": "none", "game": False,
                       "deadline_s": deadline_s or 60 * 86_400, "standard": reg["sets"][r]["name"],
                       "template": f"{reg['source']}/blob/{reg['commit']}/{m['path']}", "attribution": reg["attribution"]})
    for m in ms:
        m.update(status="open", fundings=[], attempts=[], excluded=[], history=[{"at": _now(), "what": "opened"}])
    pid = _id(template, title, _user_key(user))
    p = {"id": pid, "title": title, "template": template, "template_name": t["name"], "regulatory": regulatory, "report": report,
         "team": (team or "").strip()[:80] or None, "owner": _user_key(user), "owner_label": str(user.get("label") or "")[:80],
         "made": _now(), "milestones": ms, "cluster": "devnet", "money": "devnet test units of this app's test mint: no real money",
         "sandbox": deadline_s is not None and deadline_s <= 86_400}
    _save("projects", pid, p)
    _journal("experiment", {"project": pid, "what": "project opened", "template": template, "regulatory": regulatory, "milestones": len(ms)})
    return public_project(p)


def project(pid: str) -> dict:
    return _load("projects", pid)


def _milestone(p: dict, key: str) -> dict:
    for m in p["milestones"]:
        if m["key"] == key:
            return m
    raise Refused("milestone: not in this project")


def public_project(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k != "owner"}
    out["milestones"] = []
    for m in p["milestones"]:
        orders = [_order_public(o) for o in (_safe_order(x) for x in m["fundings"]) if o]
        locked = sum(o["units"] * o["unit_price"] for o in orders if o["status"] == "locked")
        pledged = sum(a["units"] for a in amc_of(p["id"], m["key"]) if a["status"] == "approved")
        out["milestones"].append({**{k: v for k, v in m.items() if k not in ("fundings", "excluded")},
                                  "attempts": [{k: v for k, v in a.items() if k not in ("maker_sub", "check_sub")} for a in m["attempts"]],
                                  "orders": orders, "locked_units": locked, "amc_units": pledged, "excluded_makers": len(m["excluded"]),
                                  "route": route(m)})
    return out


def projects(n: int = 50) -> list[dict]:
    return [public_project(p) for p in _all("projects")[:n]]


# ---- routing to existing capacity (B2) -------------------------------------------------------------------------------
def route(m: dict) -> dict:
    """Where this milestone's work can be bought: the knos.labs adapters (live with the maker's own key, else a labelled
    fixture quote), knos.game for code-scored work, or the maker's own shop. Work is routed only once committed money
    (escrow + AMC allowances) covers the quote: buyers commit first."""
    cap = catalogue()["capacity"].get(m.get("route") or "none", [])
    out = []
    for c in cap:
        row = {k: v for k, v in c.items()}
        if c.get("adapter"):
            try:
                from knos.labs import contract
                q = contract.adapters()[c["adapter"]].quote()
                row["quote"] = {k: q.get(k) for k in ("price", "currency", "turnaround_days", "mode", "fixture", "price_basis", "source")}
            except Exception as why:  # noqa: BLE001 - a lab that cannot quote here says why
                row["quote"] = {"error": f"{type(why).__name__}: {str(why)[:120]}"}
        out.append(row)
    return {"kind": m.get("route") or "none", "capacity": out,
            "rule": "work is ordered from a lab only when escrow + AMC commitments cover its quote; a fixture quote is labelled and never ordered"}


# ---- funding: a funder's escrow, a grant, a pool (the funder's wallet signs) ---------------------------------------
def _safe_order(oid: str) -> dict | None:
    try:
        return _load("orders", oid)
    except Refused:
        return None


def _order_public(o: dict) -> dict:
    return {k: o.get(k) for k in ("order", "project", "milestone", "units", "unit_price", "kind", "funder", "grant", "pool", "referral",
                                  "status", "signatures", "made", "deadline_s", "claim_id")} | {
        "explorer": escrow.explorer(o["order"], "address")}


def _ledger(led=None):
    return led or escrow.ledger()


def fund_tx(pid: str, key: str, units: int, account: str, kind: str = "funder", grant: dict | None = None, ref: str | None = None,
            pool: str | None = None, led=None) -> dict:
    """The devnet transaction a funder's wallet signs to lock `units` test units on one milestone (its own panel order).
    The server co-signs only the test-unit top-up (it is the test mint's authority) and keeps the pending order."""
    from solders.hash import Hash
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    from knos import chain, ideas
    from knos.ideas import commit as C
    from knos.settle.v2 import pay

    from . import blink, preorder
    if kind not in ("funder", "grant", "pool"):
        raise Refused("kind: funder, grant or pool")
    if isinstance(units, bool) or not isinstance(units, int) or not 5 <= units <= 1000:
        raise Refused("units: 5 to 1,000 test units")
    try:
        wallet = Pubkey.from_string(str(account))
    except ValueError:
        raise Refused("account: the funder's Solana wallet address") from None
    if kind == "grant":
        grant = {k: str((grant or {}).get(k) or "").strip()[:120] for k in ("agency", "id", "url")}
        if not grant["agency"] or not grant["id"]:
            raise Refused("grant: the agency and the grant's id (the award it comes from)")
    referral = load_referral(ref) if ref else None
    p = project(pid)
    m = _milestone(p, key)
    if m["status"] == "released":
        raise Refused("this milestone is already released")
    preorder._need()
    led = _ledger(led)
    authority, pan = escrow.demo_key(), preorder.panel()        # the FROST group key (1 of 1) when configured
    mint = escrow.mint(led, create=False)
    claim = ideas.claim(f"Milestone '{m['name']}' of the Knos project '{p['title']}' ({pid}, funding {len(m['fundings']) + 1})",
                        field_name=preorder.FIELD, kind="person", by={"app": "knos projects", "project": pid, "milestone": key})
    tok = pay.ata(wallet, mint)
    cap = blink._Capture(led)
    # the payee is bound when a maker claims the milestone (claim); until then the funder's own wallet stands in the
    # document (never paid: a release needs a claimed attempt, a refund always goes back to the funder)
    doc = C.commit(claim, units=units, price=1, payee=C.parse_payee(str(wallet)), funder=blink._Wallet(wallet), funder_token=tok,
                   mint=mint, led=cap, stages=[("referee_pass", 10_000)], stage_work_s=[int(m["deadline_s"])],
                   panel=pan, program=preorder.program(), demand_hash=p.get("report"), unlisted_panel=True)
    amount = units * escrow.UNIT
    setup = [pay.create_ata_ix(authority.pubkey(), w, mint) for w in (pay.FEE_OWNER,) if led.account(pay.ata(w, mint)) is None]
    if setup:
        led.send(setup, authority)
    ixs = [pay.create_ata_ix(wallet, wallet, mint)] if led.account(tok) is None else []
    ixs.append(escrow._mint_to_ix(mint, tok, authority.pubkey(), -(-(amount + pay.order_fee(amount)) // escrow.UNIT)))
    ixs += [ix for batch in cap.sent for ix in batch if ix.program_id == preorder.program()]
    bh = Hash.from_string(chain.call(led.url, "getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, wallet, bh))
    tx.partial_sign([authority], bh)
    raw = bytes(tx)
    if len(raw) > preorder.TX_BUDGET:
        raise Refused(f"the funding transaction is {len(raw)} bytes, above Knos's budget of {preorder.TX_BUDGET}")
    st = doc["orders"]["stage1"]
    o = {"order": st["order"], "project": pid, "milestone": key, "claim_id": claim["id"], "units": units, "unit_price": 1, "kind": kind,
         "funder": str(wallet), "grant": grant if kind == "grant" else None, "pool": pool,
         "referral": {"code": referral["code"], "wallet": referral["wallet"]} if referral else None,
         "status": "pending", "deadline_s": int(m["deadline_s"]), "doc": doc, "made": _now(), "signatures": {}}
    _save("orders", st["order"], o)
    with _lock:
        p = project(pid)
        _milestone(p, key)["fundings"].append(st["order"])
        _save("projects", pid, p)
    return {"transaction": base64.b64encode(raw).decode(), "bytes": len(raw), "order": st["order"], "claim_id": claim["id"],
            "message": f"Locks {units} test units on '{m['name']}' (devnet). Paid to the maker only on a result and an independent check; "
                       "refunded to you after the deadline otherwise."}


def confirm(order: str, signature: str | None = None, led=None) -> dict:
    """A pending funding becomes locked once its order account exists on chain."""
    from solders.pubkey import Pubkey
    o = _load("orders", order)
    if o["status"] == "pending":
        led = _ledger(led)
        if led.account(Pubkey.from_string(o["order"])) is None:
            raise Refused("the order is not on devnet yet: send the signed transaction first")
        o["status"] = "locked"
        if signature and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", signature):
            o["signatures"]["lock"] = signature
        _save("orders", order, o)
        with _lock:
            p = project(o["project"])
            m = _milestone(p, o["milestone"])
            if m["status"] in ("open", "reopened"):
                m["status"] = "funded"
            m["history"].append({"at": _now(), "what": f"funded {o['units']} test units ({o['kind']})", "order": order})
            _save("projects", p["id"], p)
        _journal("funding", {"project": o["project"], "milestone": o["milestone"], "order": order, "kind": o["kind"],
                             "amount_units": o["units"], "signature": o["signatures"].get("lock"), "grant": o.get("grant")})
    return _order_public(o)


def pool_txs(allocations: list[dict], units: int, account: str, ref: str | None = None, led=None) -> dict:
    """The megafund: one funder spreads `units` over many milestones of many projects, by weight. One transaction per
    milestone (each its own order), signed together by the wallet (signAllTransactions)."""
    if not isinstance(allocations, list) or not 2 <= len(allocations) <= 8:
        raise Refused("allocations: 2 to 8 {project, milestone, weight}")
    w = [max(1, int(a.get("weight") or 1)) for a in allocations]
    if isinstance(units, bool) or not isinstance(units, int) or units < 5 * len(allocations):
        raise Refused(f"units: at least 5 per milestone ({5 * len(allocations)})")
    share = [max(5, units * x // sum(w)) for x in w]
    pool = _id("pool", account)
    txs = [fund_tx(str(a["project"]), str(a["milestone"]), s, account, kind="pool", ref=ref, pool=pool, led=led)
           for a, s in zip(allocations, share)]
    _save("pools", pool, {"id": pool, "funder": account, "units": sum(share), "orders": [t["order"] for t in txs], "made": _now()})
    return {"pool": pool, "transactions": txs, "units": sum(share)}


# ---- referrals (B4) --------------------------------------------------------------------------------------------------
def make_referral(user: dict, wallet: str, target: str) -> dict:
    from solders.pubkey import Pubkey
    try:
        Pubkey.from_string(str(wallet))
    except ValueError:
        raise Refused("wallet: the referrer's Solana wallet (its share is paid there on release)") from None
    if not re.fullmatch(r"(p|b)=[0-9a-f]{16,64}", str(target or "")):
        raise Refused("target: p=<project id> or b=<report hash>")
    code = _id("ref", wallet, target)[:12]
    r = {"code": code, "wallet": str(wallet), "target": target, "by": _user_key(user), "label": str(user.get("label") or "")[:80],
         "made": _now(), "share_bps": REFERRAL_BPS}
    _save("referrals", code, r)
    return {"code": code, "link": f"/r/{code}", "share_bps": REFERRAL_BPS, "target": target,
            "rule": "when a sale or funding made through this link is released on proof, your share is a second knos_pay payee"}


def load_referral(code: str) -> dict:
    try:
        return _load("referrals", str(code))
    except Refused:
        raise Refused("ref: unknown referral code") from None


def split_payee(maker_wallet: str, referral: dict | None, maker_payee: dict | None = None) -> dict:
    """The payee of a release: the maker, and the referrer's share as a second knos_pay payee (one payee each, bps sum
    10,000). The program pays every payee named in the panel's verdicts."""
    from knos.ideas import commit as C
    base = maker_payee or C.parse_payee(maker_wallet)
    if not referral or referral.get("wallet") == maker_wallet:
        return base
    ref = C.parse_payee(referral["wallet"])
    return {**base, "split": [{"payee_id": base["payee_id"], "bps": 10_000 - REFERRAL_BPS, "wallet": base["wallet"]},
                              {"payee_id": ref["payee_id"], "bps": REFERRAL_BPS, "wallet": ref["wallet"]}]}


# ---- attempts: claim, result, independent check, release (B1) -------------------------------------------------------
def claim(pid: str, key: str, user: dict, wallet: str) -> dict:
    """A maker takes the milestone (parallel attempts allowed) and binds the wallet it is paid at."""
    from solders.pubkey import Pubkey
    try:
        Pubkey.from_string(str(wallet))
    except ValueError:
        raise Refused("wallet: your Solana wallet (the payee bound at claim)") from None
    who = _user_key(user)
    with _lock:
        p = project(pid)
        m = _milestone(p, key)
        if m["status"] == "released":
            raise Refused("this milestone is already released")
        if who in m["excluded"]:
            raise Refused("you missed this milestone's deadline once: it is reopened to other makers")
        live = [a for a in m["attempts"] if a["status"] in ("working", "result posted")]
        if any(a["maker_sub"] == who for a in live):
            raise Refused("you already have an attempt on this milestone")
        if len(live) >= MAX_ATTEMPTS:
            raise Refused(f"{MAX_ATTEMPTS} makers are already attempting this milestone")
        refs = _referee_keys()
        if wallet in refs:
            raise Refused("a referee's key cannot be a payee")
        a = {"id": _id("attempt", who, key)[:10], "maker_sub": who, "maker": str(user.get("label") or "maker")[:80], "wallet": str(wallet),
             "status": "working", "claimed": _now(), "result": None, "check": None}
        m["attempts"].append(a)
        if m["status"] in ("open", "funded", "reopened"):
            m["status"] = "claimed" if m["fundings"] else m["status"]
        m["history"].append({"at": _now(), "what": f"attempt {a['id']} claimed by {a['maker']}"})
        _save("projects", pid, p)
    _journal("experiment", {"project": pid, "milestone": key, "what": "attempt claimed", "attempt": a["id"], "payee_wallet": wallet})
    return {k: v for k, v in a.items() if k != "maker_sub"}


def _referee_keys() -> list[str]:
    keys: list[str] = []
    from . import preorder
    try:
        keys += preorder.panel()[1]
    except Exception:  # noqa: BLE001
        pass
    try:
        keys += [str(r.pubkey()) for r in preorder.referees()]
    except Exception:  # noqa: BLE001
        pass
    return keys


def _evidence_id(pid: str, key: str, attempt: str) -> str:
    return hashlib.sha256(f"{pid}|{key}|{attempt}".encode()).hexdigest()[:16]


def project_evidence(eid: str) -> bytes | None:
    """The public review page of one verified attempt (both pages' URLs and sha256s, and every funded order's claim id):
    what each FROST referee host fetches and re-checks before it signs a project milestone's release."""
    if not (isinstance(eid, str) and len(eid) == 16 and all(c in "0123456789abcdef" for c in eid)):
        return None
    f = _dir("evidence") / f"{eid}.public.json"
    return f.read_bytes() if f.exists() else None


def _claim_ids(p: dict, m: dict) -> list[str]:
    return [o["claim_id"] for o in (_safe_order(x) for x in m["fundings"]) if o and o["status"] == "locked"]


def post(pid: str, key: str, attempt: str, user: dict, url: str, role: str, fetch=None) -> dict:
    """Post evidence on an attempt: role "result" (the maker) or "check" (an independent replicator, never the maker).
    Both are fetched now; the check must come from another person on another site. Both in: the milestone releases."""
    from . import preorder
    if role not in ("result", "check"):
        raise Refused("role: result (the maker) or check (an independent replication)")
    fetch = fetch or preorder.fetch_evidence
    who = _user_key(user)
    with _lock:
        p = project(pid)
        m = _milestone(p, key)
        a = next((x for x in m["attempts"] if x["id"] == attempt), None)
        retry = a is not None and role == "check" and a["status"] == "checked" and a.get("check_sub") == who
    if retry:                                          # both pages are in and the release did not finish: send it again
        return release(pid, key, attempt)
    with _lock:
        if a is None or a["status"] not in ("working", "result posted"):
            raise Refused("attempt: not an open attempt on this milestone")
        if role == "result" and a["maker_sub"] != who:
            raise Refused("only the maker of this attempt posts its result")
        if role == "check":
            if a["maker_sub"] == who:
                raise Refused("an independent check is made by someone other than the maker")
            if not a.get("result"):
                raise Refused("the maker posts the result first")
        ids = _claim_ids(p, m)
        if not ids:
            raise Refused("this milestone has no locked funding yet: nothing to release")
        body = fetch(url)
        missing = [c for c in ids if c.encode() not in body]
        if missing:
            raise preorder.NotVerified(f"the page does not contain the milestone's claim id(s): {', '.join(missing)}")
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        if role == "check" and _site(host) == _site(a["result"]["host"]):
            raise Refused("the independent check must be published on another site than the maker's result")
        ev = {"url": url, "host": host, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "by": str(user.get("label") or "")[:80],
              "at": _now()}
        a[role] = ev
        if role == "check":
            a["check_sub"] = who
        a["status"] = "result posted" if role == "result" else "checked"
        rv = _dir("evidence") / f"{pid}-{key}-{a['id']}-{role}.page"
        rv.write_bytes(body)
        m["history"].append({"at": _now(), "what": f"{role} posted on attempt {a['id']}", "sha256": ev["sha256"]})
        _save("projects", pid, p)
    if role == "check":
        return release(pid, key, attempt)
    return {"attempt": attempt, "posted": role, "evidence": ev, "next": "an independent check of this result, by another person on another site"}


def _site(host: str) -> str:
    """The registrable part of a host, roughly (last two labels; three for well-known shared hosts)."""
    parts = host.split(".")
    shared = ("github.io", "gitlab.io", "pages.dev", "netlify.app", "vercel.app", "onrender.com", "githubusercontent.com")
    for s in shared:
        if host.endswith("." + s):
            return ".".join(parts[-3:])
    return ".".join(parts[-2:])


class _V1Ledger:
    """The ledger, sending a transaction as a v1 transaction (SIMD-0385, up to 4,096 bytes) when it does not fit the
    legacy 1,232 bytes: a verdict that pays two payees (the maker and a referrer) carries both in its signed digest."""

    def __init__(self, led):
        self.led, self.url, self.v1_sent = led, getattr(led, "url", ""), []

    def __getattr__(self, name):
        return getattr(self.led, name)

    def send(self, ixs, payer, signers=None):
        try:
            from knos import chain
            big = chain.tx_size(list(ixs), payer.pubkey(), False) > 1232
        except Exception:  # noqa: BLE001 - a ledger without size checks sends as it always did
            big = False
        if big:
            sig = self.led.send(ixs, payer, signers, v1=True) if signers else self.led.send(ixs, payer, v1=True)
            self.v1_sent.append(sig)
            return sig
        return self.led.send(ixs, payer, signers) if signers else self.led.send(ixs, payer)


def release(pid: str, key: str, attempt: str, led=None, sign=None, release_fn=None, base: str | None = None) -> dict:
    """Both pages are in: for every locked order on the milestone, the referee panel signs PASS over the pair (one
    review: the two pages' hashes and bytes) and the program pays the attempt's maker (+ the referrer's share).
    An order pinned to the FROST group key (1 of 1) is released when 2 of the 3 referee hosts have fetched the
    published review (/api/project/evidence) and signed (knos_wanted.referee); an older order pinned to the server's
    3 keys is signed by 2 of them at once. Then AMC allowances on the milestone are collected to the maker."""
    from solders.pubkey import Pubkey

    from knos.ideas import commit as C

    from . import preorder
    led = _ledger(led)
    sign = sign or C.sign
    release_fn = release_fn or C.release
    p = project(pid)
    m = _milestone(p, key)
    a = next(x for x in m["attempts"] if x["id"] == attempt)
    if a["status"] != "checked":
        raise Refused("release needs the result and its independent check")
    review = _dir("evidence") / f"{pid}-{key}-{a['id']}-review.json"
    rv = {"project": pid, "milestone": key, "attempt": a["id"], "result": a["result"], "check": a["check"],
          "rule": "result + independent check, two people, two sites"}
    review.write_text(json.dumps(rv, sort_keys=True, indent=1), encoding="utf-8")
    refs = None
    paid = []
    for oid in list(m["fundings"]):
        o = _safe_order(oid)
        if not o or o["status"] != "locked":
            continue
        if led.account(Pubkey.from_string(o["order"])) is None:
            o["status"] = "closed"
            _save("orders", oid, o)
            continue
        doc = o["doc"]
        doc["payee"] = split_payee(a["wallet"], o.get("referral"))
        if (doc.get("panel") or {}).get("m") == 1:
            paid.append(_frost_start(pid, key, a, o, rv, led, base))
            continue
        if refs is None:
            refs = preorder.referees()
        recs = [sign(doc, "stage1", r, led, passed=True, review=review) for r in refs[:2]]
        vled = _V1Ledger(led)
        got = release_fn(doc, "stage1", recs, preorder.relayer(), vled)
        if vled.v1_sent:
            o["v1_transactions"] = vled.v1_sent
        o["status"] = got["status"] if got["status"] in ("released", "refunded") else "locked"
        o["doc"] = doc
        o["paid_to"] = {"maker": a["wallet"], "referrer": (o.get("referral") or {}).get("wallet"),
                        "split": doc["payee"].get("split")}
        for i, s in enumerate(got["sent"], 1):
            o["signatures"][f"referee_{i}_pass"] = s["signature"]
        _save("orders", oid, o)
        paid.append({"order": oid, "status": o["status"], "signatures": [s["signature"] for s in got["sent"]]})
    if any(x["status"] == "signing" for x in paid):
        with _lock:
            p = project(pid)
            m = _milestone(p, key)
            m["history"].append({"at": _now(), "what": f"attempt {attempt} verified: the FROST referee group is signing", "orders": paid})
            _save("projects", pid, p)
        return {"released": paid, "amc_collected": [], "milestone": "signing",
                "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest()}
    return _settle(pid, key, attempt, paid, led, review)


def _frost_start(pid: str, key: str, a: dict, o: dict, rv: dict, led, base: str | None) -> dict:
    """Publish the attempt's review (with every funded order's claim id) and open a FROST signing session for one order."""
    from . import referee, tasks
    open_ = o.get("referee_session") or {}
    if o.get("release_attempt") == a["id"] and open_.get("id") and not open_.get("signature"):
        try:
            st = referee.coordinator().get(open_["id"]).get("state")
        except Exception:  # noqa: BLE001 - an unknown or expired session: open a new one
            st = None
        if st in ("round1", "round2"):                       # already signing: do not open a second session
            return {"order": o["order"], "status": "signing", "session": open_["id"], "evidence": open_.get("evidence")}
    if not referee.enabled():
        raise Refused("this milestone's referee group (FROST) is not configured on this server")
    eid = _evidence_id(pid, key, a["id"])
    f = _dir("evidence") / f"{eid}.public.json"
    if not f.exists():
        m = _milestone(project(pid), key)
        page = {"kind": "knos-project-milestone-review", "claims": _claim_ids(project(pid), m), **rv}
        f.write_text(json.dumps(page, sort_keys=True, indent=1), encoding="utf-8")
    url = f"{tasks.public_base(base)}/api/project/evidence?id={eid}"
    sig = referee.start({"order": o["order"], "doc": o["doc"]}, url, led, kind="project")
    o["referee_session"] = {"id": sig["session"], "github": sig["github"], "evidence": url}
    o["release_attempt"] = a["id"]
    _save("orders", o["order"], o)
    return {"order": o["order"], "status": "signing", "session": sig["session"], "evidence": url}


def frost_released(s: dict) -> dict:
    """The second FROST share of a project order's session arrived: send the group signature as the order's verdict
    (to the maker and the referrer's share, as the session's commitment says); settle the milestone when it is the last."""
    from knos.ideas import commit as C
    from knos.threshold import check

    from . import preorder
    o = _load("orders", s["meta"]["order"])
    doc, led = o["doc"], _ledger(None)
    oo = C._order(doc, "stage1", led)[1]
    v = check.verdict_record(doc, "stage1", {**s["meta"]["evidence"]}, bytes.fromhex(s["digest"]), s["signature"], s["group_key"], oo.stamp)
    vled = _V1Ledger(led)
    got = C.release(doc, "stage1", [v], preorder.relayer(), vled)
    if vled.v1_sent:
        o["v1_transactions"] = vled.v1_sent
    o["status"] = got["status"] if got["status"] in ("released", "refunded") else "locked"
    pid, key, attempt = o["project"], o["milestone"], o.get("release_attempt")
    m = _milestone(project(pid), key)
    att = next((x for x in m["attempts"] if x["id"] == attempt), {})
    o["paid_to"] = {"maker": att.get("wallet"), "referrer": (o.get("referral") or {}).get("wallet"), "split": doc["payee"].get("split")}
    o["signatures"]["referee_group_pass"] = (got["sent"] or [{}])[0].get("signature")
    o["referee_session"] = {**(o.get("referee_session") or {}), "signers": s["signers"], "signature": s["signature"]}
    _save("orders", o["order"], o)
    rest = [x for x in (_safe_order(i) for i in m["fundings"]) if x and x["status"] == "locked" and x.get("release_attempt") == attempt]
    out = {"status": o["status"], "signatures": [x["signature"] for x in got["sent"]]}
    if not rest and attempt:
        paid = [{"order": x["order"], "status": x["status"], "signatures": [x["signatures"].get("referee_group_pass")]}
                for x in (_safe_order(i) for i in m["fundings"]) if x and x.get("release_attempt") == attempt]
        out["milestone"] = _settle(pid, key, attempt, paid, led, None)["milestone"]
    return out


def _settle(pid: str, key: str, attempt: str, paid: list[dict], led, review) -> dict:
    """Every order of the verified attempt is decided: collect AMC allowances, close the other attempts, record it."""
    p = project(pid)
    a = next(x for x in _milestone(p, key)["attempts"] if x["id"] == attempt)
    collected = collect_amc(pid, key, a["wallet"], led=led)
    with _lock:
        p = project(pid)
        m = _milestone(p, key)
        aa = next(x for x in m["attempts"] if x["id"] == attempt)
        aa["status"] = "paid" if any(x["status"] == "released" for x in paid) or collected else "checked"
        for other in m["attempts"]:
            if other is not aa and other["status"] in ("working", "result posted"):
                other["status"] = "closed: another attempt was verified first"
        if aa["status"] == "paid":
            m["status"] = "released"
        m["history"].append({"at": _now(), "what": f"released to attempt {attempt}", "orders": paid, "amc": collected})
        _save("projects", pid, p)
    _journal("payout", {"project": pid, "milestone": key, "attempt": attempt, "orders": paid, "amc": collected,
                        "evidence_sha256": [a["result"]["sha256"], a["check"]["sha256"]]})
    return {"released": paid, "amc_collected": collected, "milestone": m["status"],
            "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest() if review is not None else None}


# ---- the sweeper: missed deadlines refund and reopen (B3) ------------------------------------------------------------
def sweep(led=None, refund_fn=None) -> dict:
    """Every locked order past its on-chain deadline is refunded (knos_pay RefundOrder) and its milestone reopened to
    other makers: the makers whose attempts missed it are excluded from it. Runs in the server every SWEEP_S."""
    from solders.pubkey import Pubkey

    from knos.ideas import commit as C
    from knos.settle.v2 import pay

    from . import preorder
    led = _ledger(led)
    refund_fn = refund_fn or C.refund
    done = []
    now = led.now()
    for o in _all("orders"):
        if o.get("status") != "locked":
            continue
        data = led.account(Pubkey.from_string(o["order"]))
        if data is None:
            continue
        od = pay.read_order(data)
        if od is None or now <= od.pay_until:
            continue
        try:
            got = refund_fn(o["doc"], "stage1", [], preorder.relayer(), led)
        except Exception as why:  # noqa: BLE001 - one stuck order never stops the sweep
            done.append({"order": o["order"], "error": f"{type(why).__name__}: {str(why)[:160]}"})
            continue
        o["status"] = got["status"]
        if got["sent"]:
            o["signatures"]["refund"] = got["sent"][0]["signature"]
        _save("orders", o["order"], o)
        reopened = reopen(o["project"], o["milestone"], o["order"])
        done.append({"order": o["order"], "status": o["status"], "signature": o["signatures"].get("refund"), "reopened": reopened})
        _journal("refund", {"project": o["project"], "milestone": o["milestone"], "order": o["order"],
                            "signature": o["signatures"].get("refund"), "why": "deadline passed; milestone reopened"})
    return {"swept": done, "at": _now()}


def reopen(pid: str, key: str, order: str) -> dict:
    with _lock:
        p = project(pid)
        m = _milestone(p, key)
        if m["status"] == "released":
            return {"reopened": False, "why": "released"}
        missed = [a for a in m["attempts"] if a["status"] in ("working", "result posted")]
        for a in missed:
            a["status"] = "missed the deadline"
            if a["maker_sub"] not in m["excluded"]:
                m["excluded"].append(a["maker_sub"])
        m["status"] = "reopened"
        m["history"].append({"at": _now(), "what": "deadline missed: refunded to the funder and reopened to other makers",
                             "order": order, "excluded": len(missed)})
        _save("projects", pid, p)
    return {"reopened": True, "excluded_makers": len(missed)}


_sweeper_started = False


def start_sweeper() -> None:
    global _sweeper_started
    if _sweeper_started or SWEEP_S <= 0:
        return
    _sweeper_started = True

    def loop():
        while True:
            time.sleep(SWEEP_S)
            try:
                from . import preorder
                if preorder.ready()[0] and _all("orders"):
                    got = sweep()
                    if got["swept"]:
                        print(f"knos projects sweeper: {len(got['swept'])} order(s) refunded and reopened", flush=True)
            except Exception as why:  # noqa: BLE001
                print(f"knos projects sweeper: {type(why).__name__}: {str(why)[:200]}", flush=True)
    threading.Thread(target=loop, daemon=True, name="knos-valley-sweeper").start()


# ---- AMC commitments: fund only when the milestone verifies (B2) ----------------------------------------------------
def _approve_ix(source, delegate, owner, amount: int):
    from solders.instruction import AccountMeta, Instruction
    return Instruction(_token(), bytes([4]) + struct.pack("<Q", amount),
                       [AccountMeta(source, False, True), AccountMeta(delegate, False, False), AccountMeta(owner, True, False)])


def _transfer_ix(source, dest, authority, amount: int):
    from solders.instruction import AccountMeta, Instruction
    return Instruction(_token(), bytes([3]) + struct.pack("<Q", amount),
                       [AccountMeta(source, False, True), AccountMeta(dest, False, True), AccountMeta(authority, True, False)])


def amc_tx(pid: str, key: str, units: int, account: str, led=None) -> dict:
    """An advance-market-commitment: the buyer's wallet approves the relayer to spend `units` test units from its token
    account. Nothing moves now; when the milestone verifies, the relayer pays the maker from it."""
    from solders.hash import Hash
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    from knos import chain
    from knos.settle.v2 import pay

    from . import preorder
    if isinstance(units, bool) or not isinstance(units, int) or not 1 <= units <= 1000:
        raise Refused("units: 1 to 1,000 test units")
    try:
        wallet = Pubkey.from_string(str(account))
    except ValueError:
        raise Refused("account: the buyer's Solana wallet") from None
    p = project(pid)
    m = _milestone(p, key)
    if m["status"] == "released":
        raise Refused("this milestone is already released")
    preorder._need()
    led = _ledger(led)
    authority, relayer = escrow.demo_key(), preorder.relayer()
    mint = escrow.mint(led, create=False)
    tok = pay.ata(wallet, mint)
    ixs = [pay.create_ata_ix(wallet, wallet, mint)] if led.account(tok) is None else []
    ixs.append(escrow._mint_to_ix(mint, tok, authority.pubkey(), units))
    ixs.append(_approve_ix(tok, relayer.pubkey(), wallet, units * escrow.UNIT))
    bh = Hash.from_string(chain.call(led.url, "getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, wallet, bh))
    tx.partial_sign([authority], bh)
    aid = _id("amc", account, pid, key)
    _save("amc", aid, {"id": aid, "project": pid, "milestone": key, "buyer": str(wallet), "token": str(tok), "units": units,
                       "delegate": str(relayer.pubkey()), "status": "pending", "made": _now(), "signatures": {}})
    return {"transaction": base64.b64encode(bytes(tx)).decode(), "amc": aid,
            "message": f"Commits {units} test units to '{m['name']}': an allowance from your wallet, collected only when the milestone "
                       "verifies. You can revoke it until then (an AMC is a promise, weaker than escrow)."}


def amc_confirm(aid: str, signature: str | None = None, led=None) -> dict:
    from solders.pubkey import Pubkey
    a = _load("amc", aid)
    if a["status"] == "pending":
        led = _ledger(led)
        acc = led.account(Pubkey.from_string(a["token"]))
        if acc is None or len(acc) < 121 or acc[72:76] != b"\x01\x00\x00\x00" or str(Pubkey.from_bytes(acc[76:108])) != a["delegate"]:
            raise Refused("the allowance is not on devnet yet: send the signed transaction first")
        a["status"] = "approved"
        if signature and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", signature):
            a["signatures"]["approve"] = signature
        _save("amc", aid, a)
        _journal("funding", {"project": a["project"], "milestone": a["milestone"], "amc": aid, "kind": "amc", "amount_units": a["units"],
                             "signature": a["signatures"].get("approve")})
    return {k: v for k, v in a.items()}


def amc_of(pid: str, key: str) -> list[dict]:
    return [a for a in _all("amc") if a.get("project") == pid and a.get("milestone") == key]


def collect_amc(pid: str, key: str, maker_wallet: str, led=None) -> list[dict]:
    """The milestone verified: the relayer, as delegate, pays the maker from each approved allowance (what is still
    delegated; a revoked or spent allowance pays what is left, and says so)."""
    from solders.pubkey import Pubkey

    from knos.settle.v2 import pay

    from . import preorder
    out = []
    pend = [a for a in amc_of(pid, key) if a["status"] == "approved"]
    if not pend:
        return out
    led = _ledger(led)
    relayer, mint = preorder.relayer(), escrow.mint(led, create=False)
    dest = pay.ata(Pubkey.from_string(maker_wallet), mint)
    if led.account(dest) is None:
        led.send([pay.create_ata_ix(relayer.pubkey(), Pubkey.from_string(maker_wallet), mint)], relayer)
    for a in pend:
        acc = led.account(Pubkey.from_string(a["token"]))
        left = struct.unpack("<Q", acc[121:129])[0] if acc and len(acc) >= 129 and acc[72:76] == b"\x01\x00\x00\x00" else 0
        bal = struct.unpack("<Q", acc[64:72])[0] if acc else 0
        amt = min(left, bal, a["units"] * escrow.UNIT)
        if amt <= 0:
            a["status"] = "revoked or spent before the milestone verified"
        else:
            sig = led.send([_transfer_ix(Pubkey.from_string(a["token"]), dest, relayer.pubkey(), amt)], relayer)
            a["status"], a["signatures"]["collect"], a["collected_units"] = "collected", sig, amt / escrow.UNIT
        _save("amc", a["id"], a)
        out.append({"amc": a["id"], "status": a["status"], "signature": a["signatures"].get("collect")})
    return out
