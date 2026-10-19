"""HTTP routes for projects (knos_wanted.valley), companies (knos_wanted.enterprise), evidence provenance
(knos_wanted.provenance) and the OpenAPI document. server.py hands every request here first; None = not ours.

Every route is listed once in ROUTES below (method, path, who may call it, what it takes); knos_wanted.openapi builds
/openapi.json from this table and server.ROUTES, so the document and the server cannot drift apart.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse

from . import enterprise, proofs, provenance, valley

MAX_MEDIA_BODY = provenance.MAX_MEDIA

# (method, path, signed_in, summary, body or query fields)
ROUTES = [
    ("GET", "/api/templates", False, "Milestone templates and OpenRegulatory regulatory sets", {}),
    ("GET", "/api/projects", False, "Projects, newest first", {"take": "integer"}),
    ("GET", "/api/project", False, "One project with its milestones, orders, attempts and routing", {"id": "string"}),
    ("GET", "/api/project/route", False, "Where a milestone's work can be bought (labs, knos.game) and its quotes", {"project": "string", "milestone": "string"}),
    ("POST", "/api/project", True, "Open a project from a template (+ regulatory sets); deadline_s for a one-day sandbox",
     {"template": "string", "title": "string", "regulatory": "array", "report": "string", "team": "string", "deadline_s": "integer"}),
    ("POST", "/api/sandbox", True, "A one-day devnet sandbox project from a template", {"template": "string", "title": "string", "team": "string"}),
    ("POST", "/api/project/fund", False, "Fund one milestone (funder, grant or pool): the devnet transaction a wallet signs, or with passkey=true the step your passkey approves",
     {"project": "string", "milestone": "string", "units": "integer", "account": "string", "kind": "string", "grant": "object", "ref": "string", "pool": "string", "passkey": "boolean"}),
    ("POST", "/api/project/confirm", False, "Mark a funding locked once its order is on devnet", {"order": "string", "signature": "string"}),
    ("POST", "/api/project/pool", False, "Megafund: one funder spreads units over 2-8 milestones (one transaction each)",
     {"allocations": "array", "units": "integer", "account": "string", "ref": "string"}),
    ("POST", "/api/project/amc", False, "Advance-market commitment: an allowance collected only when the milestone verifies (passkey=true: your passkey approves it)",
     {"project": "string", "milestone": "string", "units": "integer", "account": "string", "passkey": "boolean"}),
    ("POST", "/api/project/amc/confirm", False, "Mark an AMC allowance approved once it is on devnet", {"amc": "string", "signature": "string"}),
    ("POST", "/api/project/claim", True, "A maker attempts a milestone and binds its payee wallet (passkey=true: paid to your passkey wallet)", {"project": "string", "milestone": "string", "wallet": "string", "passkey": "boolean"}),
    ("POST", "/api/project/post", True, "Post a result (the maker) or an independent check (someone else, another site)",
     {"project": "string", "milestone": "string", "attempt": "string", "url": "string", "role": "string"}),
    ("POST", "/api/project/sweep", True, "Run the deadline sweeper now (it also runs every minute)", {}),
    ("POST", "/api/referral", True, "A referral link; the referrer's share is a knos_pay payee on release (passkey=true: paid to your passkey wallet)", {"target": "string", "wallet": "string", "passkey": "boolean"}),
    ("GET", "/r/{code}", False, "Follow a referral link", {}),
    ("GET", "/api/attest/key", False, "This server's ed25519 attestation key", {}),
    ("GET", "/api/attest", False, "in-toto Statement v1 in a DSSE envelope for an attempt's evidence",
     {"project": "string", "milestone": "string", "attempt": "string"}),
    ("POST", "/api/evidence/c2pa", True, "Sign a photo or video with a C2PA manifest naming the claim id (raw body; X-Claim-Id)", {}),
    ("POST", "/api/evidence/c2pa/verify", False, "Read a C2PA manifest from a photo or video (raw body)", {}),
    ("GET", "/api/sso/config", False, "Whether SAML single sign-on (SAML Jackson) is on", {}),
    ("GET", "/auth/sso", False, "Start SAML sign-in through SAML Jackson", {"tenant": "string"}),
    ("GET", "/auth/sso/callback", False, "SAML Jackson's OAuth callback", {"code": "string", "state": "string"}),
    ("POST", "/api/company/multisig", False, "The devnet transaction that creates a company's Squads multisig (its creator signs)",
     {"name": "string", "members": "array", "threshold": "integer", "creator": "string"}),
    ("POST", "/api/company/confirm", False, "Mark a company's multisig created once it is on devnet", {"company": "string", "signature": "string"}),
    ("GET", "/api/companies", False, "Companies and their multisigs", {}),
    ("GET", "/api/company/export", False, "A project's ledger as journal, Xero, QuickBooks or NetSuite CSV", {"project": "string", "format": "string"}),
    ("GET", "/api/proofs", False, "Recorded infrastructure proofs (kind + Helm, Keycloak SSO, Odoo/ERPNext/hledger imports, Sigstore), cosign-signed", {}),
    ("GET", "/api/proofs/signature", False, "The cosign (Sigstore bundle) signature of /api/proofs", {}),
    ("GET", "/api/proofs/cosign.pub", False, "The public key that signed /api/proofs", {}),
    ("GET", "/openapi.json", False, "This document", {}),
]


def _s(v, n=200):
    return v.strip()[:n] if isinstance(v, str) else None


def handle_get(h, state, u, qs) -> bool:
    q = lambda k, d="": (qs.get(k) or [d])[0]   # noqa: E731
    p = u.path
    try:
        if p == "/api/templates":
            return h._send(200, valley.templates()) or True
        if p == "/api/projects":
            return h._send(200, {"projects": valley.projects(min(100, max(1, int(q("take", "50") or 50))))}) or True
        if p == "/api/project":
            return h._send(200, valley.public_project(valley.project(q("id")))) or True
        if p == "/api/project/route":
            pr = valley.project(q("project"))
            return h._send(200, valley.route(valley._milestone(pr, q("milestone")))) or True
        if p.startswith("/r/"):
            code = p[3:]
            r = valley.load_referral(code)
            kind, _, val = r["target"].partition("=")
            to = f"/?ref={code}#" + (f"buy={val}" if kind == "b" else f"projects={val}")
            h.send_response(302)
            h.send_header("Location", to)
            h.send_header("Content-Length", "0")
            h.end_headers()
            return True
        if p == "/api/attest/key":
            return h._send(200, provenance.public_key()) or True
        if p == "/api/attest":
            return h._send(200, provenance.attest(q("project"), q("milestone"), q("attempt"))) or True
        if p in proofs.FILES:
            got = proofs.raw(p)
            return (h._send(200, got[0], got[1]) if got else h._send(404, {"error": "no recorded proofs in this build"})) or True
        if p == "/api/sso/config":
            return h._send(200, enterprise.sso_config()) or True
        if p == "/auth/sso":
            try:
                return h._redirect(enterprise.sso_start(q("tenant"), h._base())) or True
            except enterprise.SSOError as why:
                return h._redirect("/#signin_error=" + urllib.parse.quote(str(why)[:120])) or True
        if p == "/auth/sso/callback":
            try:
                s = enterprise.sso_callback(q("code"), q("state"))
                return h._redirect("/#session=" + s["token"]) or True
            except enterprise.SSOError as why:
                return h._redirect("/#signin_error=" + urllib.parse.quote(str(why)[:120])) or True
        if p == "/api/companies":
            return h._send(200, {"companies": enterprise.companies()}) or True
        if p == "/api/company/export":
            body, ctype = enterprise.export(q("project"), q("format", "journal"))
            name = f"knos-{q('project')[:16]}-{q('format', 'journal')}.csv"
            return h._send(200, body.encode(), ctype, {"Content-Disposition": f'attachment; filename="{name}"'}) or True
        if p == "/openapi.json":
            from . import openapi
            return h._send(200, openapi.document(h._base())) or True
    except (valley.Refused, ValueError, KeyError) as why:
        return h._send(400 if not str(why).endswith("unknown id") else 404, {"error": str(why)[:300]}) or True
    except Exception as why:  # noqa: BLE001 - never a dropped connection: a generic line + a log line
        import sys
        print(f"knos projects GET error {p}: {type(why).__name__}: {str(why)[:300]}", file=sys.stderr, flush=True)
        return h._send(502, {"error": "the server could not answer this; try again"}) or True
    return False


def _raw(h) -> bytes:
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > MAX_MEDIA_BODY:
        raise ValueError(f"send the photo or video as the request body (1 to {MAX_MEDIA_BODY:,} bytes)")
    return h.rfile.read(n)


POSTS = {r[1] for r in ROUTES if r[0] == "POST"}
SIGNED = {r[1] for r in ROUTES if r[0] == "POST" and r[2]}


def handle_post(h, state, path: str) -> bool:
    if path not in POSTS:
        return False
    from . import auth, preorder
    if not state.allow(h._client(), "product"):
        return h._send(429, {"error": "too many requests from this address; try again in a few minutes"}) or True
    try:
        user = auth.who(h.headers.get("Authorization"))
        if path in SIGNED and user is None:
            return h._send(401, {"error": "sign in first (passkey, SSO, Google or a guest label)"}) or True
        if path == "/api/evidence/c2pa":
            if not provenance.c2pa_available():
                return h._send(503, {"error": "C2PA signing is not installed on this server (c2pa-python)"}) or True
            mime = (h.headers.get("Content-Type") or "").split(";")[0].strip()
            return h._send(200, provenance.c2pa_sign(_raw(h), mime, str(h.headers.get("X-Claim-Id") or ""))) or True
        if path == "/api/evidence/c2pa/verify":
            if not provenance.c2pa_available():
                return h._send(503, {"error": "C2PA reading is not installed on this server (c2pa-python)"}) or True
            mime = (h.headers.get("Content-Type") or "").split(";")[0].strip()
            return h._send(200, provenance.c2pa_read(_raw(h), mime)) or True
        b = h._json()
        return h._send(200, _post(path, b, user or {}, h)) or True
    except preorder.Settled as why:
        return h._send(409, {"error": str(why)[:300]}) or True
    except preorder.NotVerified as why:
        return h._send(422, {"error": f"not verified: {why}"[:400], "verified": False}) or True
    except (valley.Refused, enterprise.SSOError, ValueError, TypeError, KeyError) as why:
        return h._send(400, {"error": str(why)[:300]}) or True
    except Exception as why:  # noqa: BLE001
        from .escrow import EscrowUnavailable
        if isinstance(why, EscrowUnavailable):
            return h._send(503, {"error": str(why)[:300]}) or True
        import hashlib
        import sys
        import time
        ref = hashlib.sha256(f"{time.time()}{id(why)}".encode()).hexdigest()[:10]
        print(f"knos projects error {ref} {path}: {type(why).__name__}: {str(why)[:300]}", file=sys.stderr, flush=True)
        return h._send(502, {"error": f"the server could not finish this step (reference {ref}); nothing was charged", "ref": ref}) or True


def _passkey(path: str, b: dict, user: dict, h) -> dict:
    """The same steps signed by the person's own passkey wallet (no browser wallet, no new account): each returns the
    step the passkey approves (static/passkey_wallet.js), relayed by POST /api/sign."""
    from . import escrow, wallets
    led, rp = escrow.ledger(), h._rp()
    pid, key = str(b.get("project", "")), str(b.get("milestone", ""))
    if path == "/api/project/fund":
        return wallets.prepare_project_fund(led, user, pid, key, b.get("units", 5), rp, str(b.get("kind") or "funder"),
                                            b.get("grant") if isinstance(b.get("grant"), dict) else None, _s(b.get("ref"), 20), _s(b.get("pool"), 64))
    if path == "/api/project/amc":
        return wallets.prepare_amc(led, user, pid, key, b.get("units", 5), rp)
    vault = str(wallets.ensure(led, wallets.holder(user), rp)["vault"])        # where a maker or referrer is paid: its passkey wallet
    if path == "/api/project/claim":
        return {**valley.claim(pid, key, user, vault), "paid_to": "your passkey wallet"}
    return {**valley.make_referral(user, vault, str(b.get("target", ""))), "paid_to": "your passkey wallet"}


PASSKEY_PATHS = ("/api/project/fund", "/api/project/amc", "/api/project/claim", "/api/referral")


def _post(path: str, b: dict, user: dict, h) -> dict:
    if b.get("passkey") is True and path in PASSKEY_PATHS:
        if not user:
            raise ValueError("sign in with your passkey first")
        return _passkey(path, b, user, h)
    if path == "/api/project/pool" and b.get("passkey") is True:
        from . import valley as v
        return {"pool": v._id("pool", str(user.get("sub"))), "rule": "fund each milestone with POST /api/project/fund {passkey, kind: pool, pool}"}
    if path == "/api/project":
        return valley.create_project(user, str(b.get("template", "")), str(b.get("title", "")), b.get("regulatory") or [],
                                     _s(b.get("report"), 64), _s(b.get("team"), 80), b.get("deadline_s"))
    if path == "/api/sandbox":
        return valley.create_project(user, str(b.get("template") or "internal_tool"), str(b.get("title") or "One-day sandbox project"), [],
                                     None, _s(b.get("team"), 80) or "sandbox team", int(os.environ.get("KNOS_SANDBOX_DEADLINE_S", "86400")))
    if path == "/api/project/fund":
        return valley.fund_tx(str(b.get("project", "")), str(b.get("milestone", "")), b.get("units", 5), str(b.get("account", "")),
                              str(b.get("kind") or "funder"), b.get("grant") if isinstance(b.get("grant"), dict) else None, _s(b.get("ref"), 20))
    if path == "/api/project/confirm":
        return valley.confirm(str(b.get("order", "")), _s(b.get("signature"), 100))
    if path == "/api/project/pool":
        return valley.pool_txs(b.get("allocations") or [], b.get("units", 0), str(b.get("account", "")), _s(b.get("ref"), 20))
    if path == "/api/project/amc":
        return valley.amc_tx(str(b.get("project", "")), str(b.get("milestone", "")), b.get("units", 5), str(b.get("account", "")))
    if path == "/api/project/amc/confirm":
        return valley.amc_confirm(str(b.get("amc", "")), _s(b.get("signature"), 100))
    if path == "/api/project/claim":
        return valley.claim(str(b.get("project", "")), str(b.get("milestone", "")), user, str(b.get("wallet", "")))
    if path == "/api/project/post":
        return valley.post(str(b.get("project", "")), str(b.get("milestone", "")), str(b.get("attempt", "")), user,
                           str(b.get("url", "")), str(b.get("role", "")))
    if path == "/api/project/sweep":
        return valley.sweep()
    if path == "/api/referral":
        return valley.make_referral(user, str(b.get("wallet", "")), str(b.get("target", "")))
    if path == "/api/company/multisig":
        members = b.get("members") or []
        if isinstance(members, str):
            members = [m.strip() for m in re.split(r"[,\s]+", members) if m.strip()]
        return enterprise.company_multisig_tx(str(b.get("name", "")), members, b.get("threshold", 1), str(b.get("creator", "")))
    if path == "/api/company/confirm":
        return enterprise.company_confirm(str(b.get("company", "")), _s(b.get("signature"), 100))
    raise ValueError("not found")


_CONFIRM = ("CONFIRM FIRST: this opens or changes work that devnet TEST money depends on. Ask the human you work for before "
            "calling, and say what it does.")
_obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}  # noqa: E731
_S, _I = {"type": "string"}, {"type": "integer"}
MCP_TOOLS = [
    {"name": "knos_templates", "title": "Milestone templates",
     "description": "AI model eval, hardware prototype, internal tool, paper to pilot, vendor deliverable; and the ISO 13485 / EU MDR "
                    "regulatory milestones from OpenRegulatory's open templates (with attribution and licence).",
     "inputSchema": _obj({})},
    {"name": "knos_projects", "title": "Projects and their milestones",
     "description": "Every project: milestones (tranches), their escrow orders, AMC commitments, attempts and where the work can be bought.",
     "inputSchema": _obj({"id": _S})},
    {"name": "knos_project_open", "title": "Open a project from a template", "description": "Opens a project; each milestone is its own "
     "tranche, released only on a result plus an independent check. " + _CONFIRM,
     "inputSchema": _obj({"template": _S, "title": _S, "regulatory": {"type": "array", "items": _S}, "session": _S}, ("template", "title", "session"))},
    {"name": "knos_project_claim", "title": "Attempt a milestone", "description": "Takes a milestone as a maker (parallel attempts allowed) "
     "and binds the wallet it pays. A missed deadline refunds the funders and reopens it to others. " + _CONFIRM,
     "inputSchema": _obj({"project": _S, "milestone": _S, "wallet": _S, "session": _S}, ("project", "milestone", "wallet", "session"))},
    {"name": "knos_project_post", "title": "Post a result or an independent check", "description": "role=result (the maker) or check (someone "
     "else, another site): a public https page containing the milestone's claim id. Both in: the referee panel releases (the FROST group: 2 of 3 independent hosts re-check and sign). " + _CONFIRM,
     "inputSchema": _obj({"project": _S, "milestone": _S, "attempt": _S, "url": _S, "role": _S, "session": _S},
                         ("project", "milestone", "attempt", "url", "role", "session"))},
    {"name": "knos_openapi", "title": "This server's OpenAPI document", "description": "The same API as REST: /openapi.json.",
     "inputSchema": _obj({})},
]


def mcp_call(name: str, args: dict, signed) -> dict:
    if name == "knos_templates":
        return valley.templates()
    if name == "knos_projects":
        return valley.public_project(valley.project(str(args["id"]))) if args.get("id") else {"projects": valley.projects(30)}
    if name == "knos_openapi":
        from . import openapi
        return openapi.document()
    who = signed(args)
    try:
        if name == "knos_project_open":
            return valley.create_project(who, str(args.get("template", "")), str(args.get("title", "")), args.get("regulatory") or [])
        if name == "knos_project_claim":
            return valley.claim(str(args.get("project", "")), str(args.get("milestone", "")), who, str(args.get("wallet", "")))
        if name == "knos_project_post":
            return valley.post(str(args.get("project", "")), str(args.get("milestone", "")), str(args.get("attempt", "")), who,
                               str(args.get("url", "")), str(args.get("role", "")))
    except valley.Refused as why:
        raise ValueError(str(why)) from None
    raise ValueError(f"unknown tool {name}")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


__all__ = ["ROUTES", "handle_get", "handle_post", "json"]
