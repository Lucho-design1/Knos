"""Knos's demand check as one service: a static page + a small JSON API, Python standard library only. Qloo is
reached ONLY from this server: its REST API (knos_wanted.qloo_rest, the primary path: POST /api/check) and, for the
older confirm-each-match flow, `qloo mcp` (knos_wanted.qloo_mcp). The browser never sees a key or calls Qloo.

    python -m knos_wanted serve            (HOST, default 127.0.0.1; PORT, default 8080)

POST /api/check {idea, place?, leader?}            the report and the code-made decision (no sign-in needed)
POST /api/wallet {}                                your passkey's wallet (made the first time); POST /api/wallet/faucet: test units
POST /api/maker/claim {report}                     the maker's passkey claims the milestone: pre-orders pay wallets it owns
POST /api/preorder {report, units}                 the challenge your passkey signs to lock test units for the maker
POST /api/sign {intent, authenticatorData, clientDataJSON, signature}   relay a passkey's answer (pre-order, factoring)
GET  /api/receivables; POST /api/lend/quote {commitment, advance_bps}; /api/factor {commitment, quote} (the maker sells);
POST /api/lend/advance {commitment}; /api/lend/collect {commitment}      factoring, every step signed by a passkey
POST /api/milestone {commitment, evidence_url}     verify the evidence; 2 of 3 referees sign PASS; release (signed in)
POST /api/refund {commitment}                      past the deadline: back to the buyer (signed in)
Rate limits per client address keep a public demo from draining the Qloo quota and the devnet test wallet.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
from collections import OrderedDict, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.parse
from urllib.parse import parse_qs, urlparse

from . import agent, auth, blink, buyer, catalog, check, company, demand, escrow, front, planner, preorder, privacy, product_routes, referee, research, tasks, valley, wallets, x402
from .qloo_mcp import AGGREGATE, Qloo, QlooUnavailable
from .qloo_rest import Client

STATIC = Path(__file__).parent / "static"


def trusted_hops() -> int:
    """KNOS_WANTED_TRUST_PROXY: how many proxies in front of this server append to X-Forwarded-For (Render: 1).
    "0", unset or not a number: none, and the header is ignored."""
    v = (os.environ.get("KNOS_WANTED_TRUST_PROXY") or "").strip()
    return int(v) if v.isdigit() and 0 < int(v) <= 8 else 0


def client_key(xff: str, peer: str) -> str:
    """The address a rate limit counts. Each trusted proxy APPENDS the address it saw, so the entry the nearest
    trusted proxy wrote is the n-th from the END; anything before it was written by the client and can be forged."""
    hops = trusted_hops()
    parts = [x.strip() for x in (xff or "").split(",") if x.strip()]
    if hops and parts:
        return parts[-hops if len(parts) >= hops else 0][:64]
    return str(peer)[:64]
MAX_BODY = 16_384
SESSION_S = 30 * 60
LIMITS = {"maker": (20, 600), "search": (40, 600), "buyer": (20, 600), "publish": (10, 600), "demo": (4, 600),
          "faucet": (2, 3600), "tx": (20, 600), "check": (12, 600), "lock": (6, 600), "auth": (30, 600),
          "milestone": (30, 600), "milestone_one": (10, 3600), "referee": (120, 600), "product": (60, 600),
          "live": (120, 600)}   # (calls, seconds) per client; "live": presence and draft autosave, apart from "product"
GLOBAL_DEMO = (60, 3600)
FRONT_ORIGINS = ("https://drexthealpha.github.io",)               # the front door, allowed to read the demand check
DEMAND_CORS = ("/api/check", "/api/demand/fields")                                           # demo pre-orders, all clients
ROUTES = {"/api/trace/keep": "check", "/api/qloo-diff": "check", "/api/maker/start": "maker", "/api/maker/search": "search", "/api/maker/confirm": "maker", "/api/maker/publish": "publish",
          "/api/buyer/start": "buyer", "/api/buyer/confirm": "buyer", "/api/preorder/demo": "demo", "/api/preorder/faucet": "faucet",
          "/api/preorder/tx": "tx", "/api/preorder/submit": "tx",
          "/api/check": "check", "/api/research": "check", "/api/cross": "check", "/api/factor": "lock",
          "/api/fund": "lock", "/api/task/submit": "check", "/api/anchor": "lock",
          "/api/auth/email": "auth", "/api/auth/email/verify": "auth", "/api/preorder": "lock", "/api/milestone": "milestone", "/api/refund": "lock",
          "/api/auth/challenge": "auth", "/api/auth/passkey/register": "auth", "/api/auth/passkey/login": "auth",
          "/api/auth/google": "auth", "/api/auth/guest": "auth",
          "/api/wallet": "tx", "/api/wallet/faucet": "faucet", "/api/sign": "tx", "/api/maker/claim": "lock", "/api/lend/quote": "lock",
          "/api/lend/advance": "lock", "/api/lend/collect": "lock"}
SIGNED_IN = ("/api/preorder", "/api/milestone", "/api/refund", "/api/factor", "/api/fund", "/api/task/submit", "/api/anchor",
             "/api/preorder/demo", "/api/preorder/faucet", "/api/preorder/tx", "/api/preorder/submit",
             "/api/wallet", "/api/wallet/faucet", "/api/sign", "/api/maker/claim", "/api/lend/quote", "/api/lend/advance", "/api/lend/collect")   # no anonymous money or faucet calls
# every GET route below (do_GET), for the OpenAPI document (knos_wanted.openapi); the product routes list their own
PAGES = {"/trace": "trace.html", "/trace.html": "trace.html", "/with-without": "with_without.html", "/with-without.html": "with_without.html",
         "/qloo-safe-use": "qloo_safe_use.html", "/qloo-safe-use.html": "qloo_safe_use.html", "/invite": "invite.html", "/invite.html": "invite.html"}
GET_ROUTES = {"/actions.json": "Solana Actions rules", "/api/trace": "A demand report's Qloo calls, redacted: endpoint, params, ids, excerpt, limit",
              "/api/qloo-diff": "The \"With and without Qloo\" table: 20 ideas, each checked with Qloo and with the key unset", "/sw.js": "The app's service worker (offline shell, background sync)",
              "/manifest.webmanifest": "The app's web app manifest (installable, home-screen shortcuts)", "/api/actions/preorder": "Solana Action (Blink): pre-order metadata",
              "/api/pay/fund": "Solana Pay transaction request: the label and icon a wallet shows before funding a milestone",
              "/api/cross": "Poll a live crossing", "/verify": "How we verify", "/api/crossings": "Crossings, newest first",
              "/api/front": "Research products open for backing now (the front door's list; ?slug= one product)",
              "/api/demand/fields": "The Qloo demand families F1-F8: every option's name, Qloo parameter, kind, help and example",
              "/api/tasks": "Open contributor rounds (knos.game)", "/api/memory/search": "Search the agent's memory (Sibyl)",
              "/api/x402/report": "A demand report, paid per read over x402", "/api/commitments": "Pre-orders and funder escrows",
              "/mcp": "MCP discovery page (POST JSON-RPC here)", "/auth/orcid": "Sign in with ORCID", "/auth/orcid/callback": "ORCID callback",
              "/": "The app", "/api/status": "Server status", "/api/products": "Listed products", "/api/quote": "Fee quote",
              "/api/pool": "A report's pre-order pool", "/healthz": "Health check", "/api/report": "A demand report",
              "/api/commitment": "One commitment", "/api/auth/config": "Sign-in providers", "/api/fees": "Fees (config/fees.yaml)",
              "/api/receivables": "Receivables a lender can finance (passkey wallets, Huma-style terms)",
              "/api/referee/group": "The FROST referee group (public)", "/api/referee/pending": "Open referee signing sessions",
              "/api/referee/session": "One referee signing session", "/api/prize/evidence": "A demo prize's public evidence (the round's verdict)",
              "/api/project/evidence": "A project attempt's public review (both pages and the claim ids)"}
SUMMARIES = {"/api/check": "Demand check on Qloo", "/api/research": "Research card from a paper id", "/api/cross": "Start a crossing",
             "/api/preorder": "Pre-order on proof", "/api/milestone": "Post milestone evidence; 2 of 3 referees release",
             "/api/refund": "Refund past the deadline", "/api/fund": "Fund a milestone", "/api/factor": "Receivable financing offer",
             "/api/anchor": "Anchor the record root on devnet", "/api/task/submit": "Submit to a contributor round"}


class State:
    def __init__(self, q: Qloo | None = None, rest: Client | None = None):
        self.q = q or Qloo()
        self.rest = rest or Client()
        self.cards: dict[str, dict] = {}
        self.last_anchor: dict | None = None
        self.reports: OrderedDict[str, dict] = OrderedDict()
        self.sessions: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()
        self.qlock = threading.Lock()        # one Qloo conversation at a time over the one bridge

    def allow(self, client: str, kind: str) -> bool:
        n, window = LIMITS[kind]
        now = time.monotonic()
        with self.lock:
            checks = [((client, kind), n, window)] + ([(("*", "demo"), *GLOBAL_DEMO)] if kind == "demo" else [])
            for key, cap, win in checks:
                d = self.hits[key]
                while d and now - d[0] > win:
                    d.popleft()
                if len(d) >= cap:
                    return False
            for key, _, _ in checks:
                self.hits[key].append(now)
            return True

    def keep(self, r: dict) -> None:
        with self.lock:
            self.reports[r["hash"]] = r
            while len(self.reports) > 500:
                self.reports.popitem(last=False)

    def report(self, h) -> dict | None:
        with self.lock:
            got = self.reports.get(h) if isinstance(h, str) else None
        if got is None and isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h):
            f = escrow._state_dir() / "reports" / f"{h}.report"       # a decision report kept across restarts
            if f.exists():
                got = json.loads(f.read_text(encoding="utf-8"))
        return got

    def keep_check(self, r: dict) -> None:
        self.keep(r)
        d = escrow._state_dir() / "reports"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{r['hash']}.report").write_text(json.dumps(r, default=str), encoding="utf-8")

    def known(self, h) -> bool:
        return self.report(h) is not None or (isinstance(h, str) and catalog.get(h) is not None)

    def session(self, s: dict | None = None, sid: str | None = None, flow: str | None = None) -> dict:
        now = time.monotonic()
        with self.lock:
            for k in [k for k, (t, _) in self.sessions.items() if now - t > SESSION_S]:
                self.sessions.pop(k)
            if s is not None:
                self.sessions[s["id"]] = (now, s)
                while len(self.sessions) > 500:
                    self.sessions.popitem(last=False)
                return s
            got = self.sessions.get(sid or "")
        if got is None or (flow and got[1].get("flow") != flow):
            raise ValueError("unknown or expired session: start again")
        return got[1]


def _names(v, n: int = 3) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,;\n]", v)
    return [s.strip()[:60] for s in (v or []) if isinstance(s, str) and s.strip()][:n]


def _text(v, n: int = 60) -> str | None:
    return v.strip()[:n] if isinstance(v, str) and v.strip() else None


def make_handler(state: State):
    class H(BaseHTTPRequestHandler):
        server_version = "knos-demand-check/0.3.33"

        def log_message(self, fmt, *args):  # no request logging: ideas and tastes are the visitor's; keys are never in URLs
            pass

        def _client(self) -> str:
            return client_key(self.headers.get("X-Forwarded-For", ""), self.client_address[0])

        def _send(self, code: int, body, ctype: str = "application/json", headers: dict | None = None) -> None:
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            # the front door (GitHub Pages) runs the same demand check from the browser: these answers, to that origin only,
            # never with credentials (no sign-in is needed to check demand)
            if urlparse(self.path).path in DEMAND_CORS and self.headers.get("Origin") in FRONT_ORIGINS and "Access-Control-Allow-Origin" not in (headers or {}):
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("request too large")
            got = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(got, dict):
                raise ValueError("send a JSON object")
            return got

        def _base(self) -> str:
            host = self.headers.get("Host") or "localhost"
            proto = "https" if trusted_hops() or not host.startswith(("127.", "localhost")) else "http"
            return f"{proto}://{host}"

        def _redirect(self, to: str) -> None:
            self.send_response(302)
            self.send_header("Location", to)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_OPTIONS(self):
            return self._send(204, b"", "text/plain", blink.CORS)

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if product_routes.handle_get(self, state, u, qs):
                return None
            if u.path == "/actions.json":
                return self._send(200, blink.RULES, headers=blink.CORS)
            if u.path == "/api/actions/preorder":
                rep = state.report((qs.get("report") or [""])[0])
                if rep is None:
                    return self._send(404, {"message": "unknown report"}, headers=blink.CORS)
                return self._send(200, blink.action(rep, self._base()), headers=blink.CORS)
            if u.path == blink.PAY_PATH:
                return self._send(200, blink.pay_get(self._base()), headers=blink.CORS)
            if u.path == "/api/cross":
                got = agent.poll((qs.get("id") or [""])[0], int((qs.get("since") or ["0"])[0] or 0))
                return self._send(200 if got else 404, got or {"error": "unknown crossing"})
            if u.path in ("/verify", "/verify.html"):
                return self._send(200, (STATIC / "verify.html").read_bytes(), "text/html; charset=utf-8")
            if u.path in PAGES:                              # the trace, "With and without Qloo", Qloo safe use, the invite
                return self._send(200, (STATIC / PAGES[u.path]).read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/trace":                       # a report's Qloo calls, redacted (knos_wanted.trace)
                from . import trace as _trace
                t = _trace.load(state, (qs.get("hash") or [""])[0])
                return self._send(200 if t else 404, t or {"error": "unknown report: no trace kept for it"})
            if u.path == "/api/qloo-diff":                   # the table behind "With and without Qloo"
                try:
                    return self._send(200, valley._load("pages", "qloo_diff"))
                except valley.Refused:
                    return self._send(404, {"error": "the table has not been published yet"})
            if u.path == "/api/demand/fields":               # one table for every interface's controls (knos.qloo_families)
                from . import families as _fam
                return self._send(200, _fam.fields())
            if u.path == "/api/front":                       # the front door's list (web/home.js asks it from github.io)
                slug = (qs.get("slug") or [""])[0]
                if slug:
                    got = front.resolve(state, slug)
                    return self._send(200 if got else 404, got or {"error": "unknown product"}, headers=front.CORS)
                return self._send(200, front.board(state), headers=front.CORS)
            if u.path == "/api/crossings":
                take = min(100, max(1, int((qs.get("take") or ["30"])[0] or 30)))
                offset = max(0, int((qs.get("offset") or ["0"])[0] or 0))
                rows = agent.crossings(state, offset + take)[offset:]
                return self._send(200, {"crossings": rows, "take": take, "offset": offset})
            if u.path == "/api/tasks":
                return self._send(200, tasks.listing())
            if u.path == "/api/memory/search":
                q = (qs.get("q") or [""])[0][:200]
                if not q.strip():
                    return self._send(400, {"error": "q: what to search the record for"})
                try:
                    from knos.record import search as rsearch
                    got = rsearch.search(q, root=company.root())
                    return self._send(200, {"query": q, "said": got.get("said"), "verdict": got.get("verdict"),
                                            "rows": [{k: r.get(k) for k in ("tier", "key", "category", "name", "doc_key", "snippet", "score")}
                                                     for r in got.get("rows", [])[:20]]})
                except Exception as why:  # noqa: BLE001
                    return self._send(503, {"error": f"the record cannot be searched here ({type(why).__name__})"})
            if u.path == "/api/x402/report":
                h = (qs.get("hash") or [""])[0]
                rep_ = state.report(h)
                if rep_ is None:
                    return self._send(404, {"error": "unknown report"})
                if not x402.ready():
                    return self._send(503, {"error": "the paid route needs the devnet escrow configured"})
                pay_h = self.headers.get("PAYMENT-SIGNATURE")
                try:
                    if not pay_h:
                        ch = x402.challenge(h, self._base())
                        return self._send(402, ch, headers={"PAYMENT-REQUIRED": x402.header(ch)})
                    settled = x402.settle(pay_h)
                except ValueError as why:
                    ch = {**x402.challenge(h, self._base()), "error": str(why)[:200]}
                    return self._send(402, ch, headers={"PAYMENT-REQUIRED": x402.header(ch)})
                return self._send(200, {**rep_, "paid": settled}, headers={"PAYMENT-RESPONSE": x402.header(settled)})
            if u.path == "/api/receivables":
                return self._send(200, {"receivables": wallets.receivables(), "money": wallets.MONEY,
                                        "model": "PayFi receivable financing (as Huma Finance): advance rate, fee, due date, repaid by the release"})
            if u.path == "/api/commitments":
                take = min(100, max(1, int((qs.get("take") or ["50"])[0] or 50)))
                offset = max(0, int((qs.get("offset") or ["0"])[0] or 0))
                return self._send(200, {"commitments": preorder.all_public(offset + take)[offset:], "take": take, "offset": offset})
            if u.path == "/mcp":
                if "text/html" in (self.headers.get("Accept") or ""):
                    return self._send(200, agent.DISCOVERY.encode(), "text/html; charset=utf-8")
                return self._send(405, {"error": "POST JSON-RPC messages to /mcp (MCP Streamable HTTP)"}, headers={"Allow": "POST"})
            if u.path == "/auth/orcid":
                try:
                    return self._redirect(auth.orcid_authorize(self._base() + "/auth/orcid/callback"))
                except auth.AuthError as why:
                    return self._send(404, {"error": str(why)})
            if u.path == "/auth/orcid/callback":
                try:
                    s_ = auth.orcid_callback((qs.get("code") or [""])[0], (qs.get("state") or [""])[0], self._base() + "/auth/orcid/callback")
                    return self._redirect("/#session=" + s_["token"])
                except auth.AuthError as why:
                    return self._redirect("/#signin_error=" + urllib.parse.quote(str(why)[:120]))
            if u.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path in ("/sw.js", "/manifest.webmanifest"):        # the PWA: its worker's scope is the whole app
                ctype = "text/javascript; charset=utf-8" if u.path == "/sw.js" else "application/manifest+json"
                return self._send(200, (STATIC / u.path[1:]).read_bytes(), ctype, {"Cache-Control": "no-cache"})
            if u.path.startswith("/static/"):
                f = (STATIC / u.path[len("/static/"):]).resolve()
                if STATIC.resolve() in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                return self._send(404, {"error": "not found"})
            if u.path == "/api/status":
                return self._send(200, self.status())
            if u.path == "/api/products":
                return self._send(200, {"products": catalog.products(), "aggregate": AGGREGATE})
            if u.path == "/api/quote":
                try:
                    units = int((qs.get("units") or ["5"])[0])
                    escrow._amount(units) if escrow.available() else None
                    return self._send(200, company.quote(units))
                except (ValueError, TypeError) as why:
                    return self._send(400, {"error": str(why)})
            if u.path == "/api/pool":
                h = (qs.get("hash") or [""])[0]
                try:
                    return self._send(200, escrow.pool(h))
                except escrow.EscrowUnavailable as why:
                    return self._send(503, {"error": str(why)})
                except Exception as why:  # noqa: BLE001
                    return self._send(400, {"error": f"{type(why).__name__}: {why}"[:300]})
            if u.path == "/healthz":
                return self._send(200, {"ok": True})
            if u.path == "/api/report":
                rep = state.report((qs.get("hash") or [""])[0])
                if rep is None:
                    return self._send(404, {"error": "unknown report"})
                return self._send(200, {**rep, "preorders": preorder.of_report(rep["hash"]),
                                        "reserve": preorder.reserve_status(rep) if rep.get("kind") == check.KIND else None})
            if u.path == "/api/commitment":
                try:
                    rec = preorder.load((qs.get("id") or [""])[0])
                    try:
                        rec = blink.refresh(rec)
                    except Exception:  # noqa: BLE001 - the chain is unreachable: show what the server holds
                        pass
                    return self._send(200, preorder.public(rec))
                except ValueError as why:
                    return self._send(404, {"error": str(why)})
            if u.path == "/api/auth/config":
                return self._send(200, auth.config())
            if u.path == "/api/fees":
                return self._send(200, preorder.fee_line())
            if u.path.startswith("/api/referee/"):            # the FROST referee hosts (knos_wanted.referee)
                return self._send(*referee.get(u.path, qs))
            if u.path == "/api/project/evidence":             # a project attempt's public review (both pages, claim ids)
                page = valley.project_evidence((qs.get("id") or [""])[0])
                return self._send(200, page, "application/json") if page else self._send(404, {"error": "unknown evidence"})
            if u.path == "/api/prize/evidence":               # a demo prize's public evidence: the round's verdict
                page = tasks.prize_evidence((qs.get("id") or [""])[0])
                return self._send(200, page, "application/json") if page else self._send(404, {"error": "unknown prize"})
            return self._send(404, {"error": "not found"})

        def status(self) -> dict:
            pf = preorder.preflight_status()
            rest = state.rest.status()
            mcp = state.q.status()
            if rest["rest"]:        # the decision path is Qloo's REST API: when it is live, the server is live
                top = {"mode": "live", "label": check.LIVE_LABEL, "reason": "Qloo REST API key configured on this server",
                       "mcp_flow": {k: mcp.get(k) for k in ("mode", "label", "reason")}}
            else:
                top = {"no_key_behaviour": "every check answers CANNOT_DECIDE (" + check.NO_EVIDENCE + "); pre-orders never open"}
            return {**mcp, **top, "qloo_rest": rest, "preorders": pf, "record_anchor": state.last_anchor,
                    "x402": {"ready": x402.ready(), "route": "/api/x402/report?hash=<report>", "price": f"{x402.PRICE_UNITS} test unit per read"},
                    "fees": preorder.fee_line(), "auth": auth.config(),
                    "framing": demand.FRAMING, "escrow": escrow.available(),
                    "demo_wallet": bool(os.environ.get("KNOS_WANTED_DEVNET_KEYPAIR")), "cluster": "devnet",
                    "record": company.root() is not None, "targets": ["brand", "place", "artist", "movie", "book", "podcast", "tv_show"]}

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/mcp":
                return self._mcp()
            if u.path in ("/api/actions/preorder", blink.PAY_PATH):
                return self._action(u)
            if u.path in ("/api/referee/commit", "/api/referee/share", "/api/referee/attest"):   # a referee host's FROST round (signed by its transport key)
                if not state.allow(self._client(), "referee"):
                    return self._send(429, {"error": "too many referee posts from this address"})
                try:
                    return self._send(*referee.post(u.path, self._json()))
                except ValueError as why:
                    return self._send(400, {"error": str(why)[:200]})
            if product_routes.handle_post(self, state, u.path):
                return None
            kind = ROUTES.get(u.path)
            if kind is None:
                return self._send(404, {"error": "not found"})
            if not state.allow(self._client(), kind):
                return self._send(429, {"error": "too many requests from this address; try again in a few minutes"})
            try:
                body = self._json()
                self.user = auth.who(self.headers.get("Authorization"))
                if u.path in SIGNED_IN and self.user is None:
                    return self._send(401, {"error": "sign in first (passkey, Google or a guest label)"})
                if u.path == "/api/milestone" and not state.allow("commitment:" + str(body.get("commitment", ""))[:64], "milestone_one"):
                    return self._send(429, {"error": "this commitment had 10 evidence posts in the last hour; try again later"})
                if u.path.startswith("/api/auth/") or u.path in ("/api/check", "/api/research", "/api/cross", "/api/trace/keep", "/api/qloo-diff") + SIGNED_IN:
                    return self._send(200, self.route_v2(u.path, body))
                return self._send(200, self.route(u.path, body))
            except (auth.AuthError, wallets.NeedPasskey) as why:
                return self._send(401, {"error": str(why)[:300], "needs": "passkey" if isinstance(why, wallets.NeedPasskey) else None})
            except preorder.Settled as why:
                return self._send(409, {"error": str(why)[:300], "refused_by": "the escrow order on devnet (read from the chain)"})
            except preorder.NotVerified as why:
                return self._send(422, {"error": f"milestone not verified: {why}"[:400], "verified": False})
            except escrow.EscrowUnavailable as why:
                return self._send(503, {"error": str(why)})
            except QlooUnavailable as why:
                return self._send(503, {"error": f"Qloo MCP: {why}"})
            except (privacy.PersonalData, demand.FlowError, planner.PlanError) as why:
                return self._send(400, {"error": str(why)[:400]})
            except (ValueError, TypeError, KeyError) as why:
                return self._send(400, {"error": str(why)[:300]})
            except Exception as why:  # noqa: BLE001 - never a raw Python error to the user: a generic line + a log line
                ref = hashlib.sha256(f"{time.time()}{id(why)}".encode()).hexdigest()[:10]
                print(f"knos-demand-check error {ref} {u.path}: {type(why).__name__}: {str(why)[:300]}", file=sys.stderr, flush=True)
                return self._send(502, {"error": f"the server could not finish this step (reference {ref}); nothing was charged", "ref": ref})

        def _origin(self) -> tuple[str, str]:
            host = (self.headers.get("Host") or "").split(":")[0]
            rp_id = os.environ.get("KNOS_WANTED_RP_ID") or host
            origin = self.headers.get("Origin") or ""
            o = urlparse(origin)
            if o.hostname != rp_id or (o.scheme != "https" and rp_id not in ("localhost", "127.0.0.1")):
                raise auth.AuthError("passkeys work only on this site's own https origin (or localhost)")
            return origin, rp_id

        def _mcp(self):
            try:
                msg = self._json()
            except ValueError as why:
                return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(why)[:200]}})
            if not state.allow(self._client(), "check"):
                return self._send(429, {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32000, "message": "rate limited"}})
            out = agent.mcp(state, msg)
            if out is None:
                return self._send(202, b"", "text/plain")
            return self._send(200, out, headers={"Mcp-Session-Id": "knos"} if msg.get("method") == "initialize" else None)

        def _action(self, u):
            qs = parse_qs(u.query)
            if not state.allow(self._client(), "lock"):
                return self._send(429, {"message": "too many pre-orders from this address; try again later"}, headers=blink.CORS)
            try:
                body = self._json()
                if u.path == blink.PAY_PATH:                    # Solana Pay: fund a milestone from any wallet
                    one = lambda k: (qs.get(k) or [""])[0]  # noqa: E731
                    return self._send(200, blink.pay_post(one("project"), one("milestone"), int(one("units") or 5), str(body.get("account", ""))),
                                      headers=blink.CORS)
                rep = state.report((qs.get("report") or [""])[0])
                if rep is None:
                    raise ValueError("unknown report")
                units = int((qs.get("units") or ["5"])[0])
                return self._send(200, blink.preorder_tx(rep, str(body.get("account", "")), units), headers=blink.CORS)
            except (ValueError, TypeError, escrow.EscrowUnavailable) as why:
                return self._send(400, {"message": str(why)[:300]}, headers=blink.CORS)
            except Exception as why:  # noqa: BLE001
                print(f"knos-demand-check action error: {type(why).__name__}: {str(why)[:300]}", file=sys.stderr, flush=True)
                return self._send(500, {"message": "the server could not build this transaction"}, headers=blink.CORS)

        def route_v2(self, path: str, body: dict) -> dict:
            """Knos's demand check on Qloo's REST API, pre-orders paid on proof, and sign-in."""
            if path == "/api/cross":
                ref, idea = _text(body.get("ref"), 200), _text(body.get("idea"), 500)
                privacy.check({"idea": idea, "place": body.get("place")})
                from knos import qloo_families
                opts = {k: body[k] for k in qloo_families.FIELDS if k in body}
                privacy.check({k: v for k, v in opts.items() if isinstance(v, str)})
                job = agent.start(state, ref=ref, idea=idea, place=_text(body.get("place")), product=_text(body.get("product"), 200),
                                  options=opts)
                return {"id": job["id"], "status": job["status"]}
            if path == "/api/auth/email":
                return auth.email_link(str(body.get("email") or ""), self._base())
            if path == "/api/auth/email/verify":
                return auth.email_verify(str(body.get("token") or ""))
            user = self.user or {}
            if path in ("/api/factor", "/api/wallet", "/api/wallet/faucet", "/api/maker/claim", "/api/lend/quote", "/api/lend/advance",
                        "/api/lend/collect", "/api/sign"):
                return self.money(path, body, user)
            if path == "/api/fund":
                rep = state.report(body.get("report") or body.get("hash"))
                if rep is None or rep.get("kind") != check.KIND:
                    raise ValueError("unknown report: run the crossing first")
                return wallets.prepare_preorder(escrow.ledger(), user, rep, body.get("units", 5), self._rp(), funder=True)
            if path == "/api/anchor":
                got = company.anchor()
                if got.get("anchored"):
                    state.last_anchor = {"tx": got["tx"], "explorer": got["explorer"], "root": got["root"]}
                return got
            if path == "/api/task/submit":
                return tasks.submit(str(body.get("round", "")), str(body.get("name", "")), str(body.get("code", "")),
                                    f"{user.get('kind')}: {user.get('label')}", sub=str(user.get("sub") or ""),
                                    wallet=_text(body.get("wallet"), 44), base=self._base())
            if path == "/api/check":
                idea = body.get("idea")
                if not isinstance(idea, str) or not idea.strip():
                    raise ValueError("describe the idea")
                privacy.check({"idea": idea, "place": body.get("place"), "leader": body.get("leader")})
                ex = body.get("exclude") or []
                if not isinstance(ex, list) or len(ex) > 20 or not all(isinstance(x, str) and len(x) < 80 for x in ex):
                    raise ValueError("exclude: a list of up to 20 Qloo entity ids the maker unticked")
                from knos import qloo_families
                opts = {k: body[k] for k in qloo_families.FIELDS if k in body and k != "exclude"}   # the families' fields, by name
                if ex:
                    opts["exclude"] = ",".join(ex)
                privacy.check({k: v for k, v in opts.items() if isinstance(v, str)})
                without = body.get("without_qloo") is True        # the same check with the key unset (the comparison)
                rep = check.demand_check(idea, _text(body.get("place")), _text(body.get("leader"), 80),
                                         client=Client(key="") if without else state.rest, exclude=ex, options=opts)
                if without:
                    rep["without_qloo"] = True
                rep["fees"] = preorder.fee_line()
                card = state.cards.get(str(body.get("research") or ""))
                if card:
                    rep["research"] = {**card, "why_never_crossed": research.why_never_crossed(card, rep)}
                rep["record"] = company.record_check(rep)          # the decision in the agent's memory (Sibyl)
                state.keep_check(rep)
                return rep
            if path == "/api/trace/keep":                   # keep a report's trace on devnet: something links to it
                from . import trace as _trace
                return _trace.keep(state, str(body.get("hash") or ""))
            if path == "/api/qloo-diff":                     # the operator publishes the "With and without Qloo" table
                if not product_routes._admin(self.headers.get("X-Knos-Admin")):
                    raise auth.AuthError("the operator's X-Knos-Admin key publishes this table")
                rows = body.get("rows")
                if not isinstance(rows, list) or not 1 <= len(rows) <= 60:
                    raise ValueError("rows: 1 to 60")
                doc = {"v": 1, "made": body.get("made"), "summary": body.get("summary"), "rows": rows, "rule": body.get("rule")}
                valley._save("pages", "qloo_diff", doc)
                return {"published": len(rows), "page": "/with-without"}
            if path == "/api/research":
                card = research.research_card(str(body.get("ref") or ""), product=_text(body.get("product"), 200))
                with state.lock:
                    state.cards[card["hash"]] = card
                    while len(state.cards) > 300:
                        state.cards.pop(next(iter(state.cards)))
                return card
            if path == "/api/auth/challenge":
                return {"challenge": auth.challenge(), "rp_id": os.environ.get("KNOS_WANTED_RP_ID") or (self.headers.get("Host") or "").split(":")[0]}
            if path == "/api/auth/passkey/register":
                origin, _ = self._origin()
                return auth.register(body, origin, str(body.get("label") or ""))
            if path == "/api/auth/passkey/login":
                origin, rp_id = self._origin()
                return auth.login(body, origin, rp_id)
            if path == "/api/auth/google":
                return auth.google(body.get("credential"))
            if path == "/api/auth/guest":
                return auth.guest(str(body.get("label") or ""))
            if path == "/api/preorder":
                rep = state.report(body.get("report") or body.get("hash"))
                if rep is None or rep.get("kind") != check.KIND:
                    raise ValueError("unknown report: run the demand check first")
                return wallets.prepare_preorder(escrow.ledger(), user, rep, body.get("units", 5), self._rp())
            rec = preorder.load(str(body.get("commitment", "")))
            rec = blink.refresh(rec)
            if path == "/api/milestone":
                return preorder.milestone(state.report(rec["report"]) or {}, rec["order"], str(body.get("evidence_url", "")))
            return preorder.refund(rec["order"])

        def _rp(self) -> str:
            return os.environ.get("KNOS_WANTED_RP_ID") or (self.headers.get("Host") or "").split(":")[0]

        def money(self, path: str, body: dict, user: dict) -> dict:
            """Every step that moves money is signed by the person's own passkey (knos_wanted.wallets)."""
            led = escrow.ledger()
            if path == "/api/sign":
                return wallets.sign(led, user, body)
            h = wallets.holder(user)
            if path == "/api/wallet":
                return wallets.public(led, h, self._rp())
            if path == "/api/wallet/faucet":
                return wallets.faucet(led, h, self._rp())
            if path == "/api/maker/claim":
                rep = state.report(body.get("report") or body.get("hash"))
                if rep is None or rep.get("kind") != check.KIND:
                    raise ValueError("unknown report: run the demand check first")
                return wallets.claim_maker(led, user, rep, self._rp())
            c = str(body.get("commitment", ""))
            if path == "/api/factor":
                return wallets.prepare_accept(led, user, c, str(body.get("quote", "")))
            if path == "/api/lend/quote":
                return wallets.quote(led, user, c, body.get("advance_bps", 9000), self._rp())
            if path == "/api/lend/advance":
                return wallets.prepare_advance(led, user, c, self._rp())
            return wallets.prepare_collect(led, user, c, self._rp())

        def route(self, path: str, body: dict) -> dict:
            if path == "/api/maker/start":
                idea = body.get("idea")
                if not isinstance(idea, str) or not idea.strip():
                    raise ValueError("describe the idea")
                with state.qlock:
                    s = demand.start(state.q, idea, _names(body.get("rivals")), _text(body.get("place")), _names(body.get("variants")) or None)
                return state.session(s)
            if path == "/api/maker/search":
                s = state.session(sid=body.get("session"), flow="maker")
                name = _text(body.get("name"))
                if not name:
                    raise ValueError("type a name to look up")
                with state.qlock:
                    return {"question": demand.search(state.q, s, str(body.get("key", "")), name), "trail": s["trail"]}
            if path == "/api/maker/confirm":
                s = state.session(sid=body.get("session"), flow="maker")
                if not isinstance(body.get("choices"), dict):
                    raise ValueError("choices: an object")
                with state.qlock:
                    rep = demand.confirm(state.q, s, body["choices"])
                rep["record"] = company.record_report(rep)
                state.keep(rep)
                return rep
            if path == "/api/maker/publish":
                rep = state.report(body.get("hash"))
                if rep is None:
                    raise ValueError("unknown report: build the report first")
                return {"product": catalog.publish(rep, str(body.get("title", ""))), "quote": company.quote(5)}
            if path == "/api/buyer/start":
                with state.qlock:
                    return state.session(buyer.start(state.q, body.get("likes"), body.get("vibes"), body.get("targets")))
            if path == "/api/buyer/confirm":
                s = state.session(sid=body.get("session"), flow="buyer")
                if not isinstance(body.get("choices"), dict):
                    raise ValueError("choices: an object")
                with state.qlock:
                    return buyer.confirm(state.q, s, body["choices"])
            h = body.get("hash")
            if path == "/api/preorder/faucet":
                return escrow.faucet(str(body.get("owner", "")))
            if not state.known(h):
                raise ValueError("unknown report: build the report or pick a listed product first")
            units = body.get("units", 5)
            if path == "/api/preorder/tx":
                return escrow.wallet_tx(h, str(body.get("owner", "")), units)
            if path == "/api/preorder/demo":
                raise ValueError("removed: no server key buys for anyone; a pre-order is signed by your own passkey (POST /api/preorder) "
                                 "or your own wallet (POST /api/preorder/tx)")
            res = escrow.submit(str(body.get("transaction", "")), str(body.get("owner", "")))
            res.update(owner=str(body.get("owner", "")), amount_units=units, order=body.get("order"), buyer_kind="wallet")
            rep = state.report(h) or catalog.get(h) or {}
            q = company.quote(units)
            res["fees"] = q
            res["record"] = company.record_preorder(h, res, q, synthetic_report=rep.get("mode") != "live")
            if res["record"].get("recorded") and os.environ.get("KNOS_WANTED_DEVNET_KEYPAIR") and os.environ.get("KNOS_WANTED_ANCHOR", "1") == "1":
                res["anchor"] = company.anchor()
            return res

    return H


def _restore_projects(budget_s: float = 60.0) -> None:
    """A redeploy starts on an empty disk: read the projects back from their devnet records (knos_wanted.chainstate),
    within `budget_s`; a failure is said in the log and the app starts anyway."""
    from . import chainstate
    if not chainstate.on() or any(valley._dir("projects").glob("*.json")):
        return
    box: dict = {}

    def run():
        try:
            from . import trace as _trace

            def put(kind, key, obj):
                if kind == "projects":
                    valley._save(kind, key, obj, chain=False)
                elif kind == "traces":
                    _trace.restore_save(kind, key, obj)
                else:
                    valley._save(kind, key, obj, chain=False)
            box["n"] = chainstate.restore(put)
        except Exception as why:  # noqa: BLE001
            box["error"] = f"{type(why).__name__}: {str(why)[:200]}"
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(budget_s)
    print(f"knos chainstate: restored {box.get('n', 0)} project(s) from devnet" + (f"; {box['error']}" if "error" in box else "")
          + ("" if not t.is_alive() else f"; still reading after {budget_s:.0f} s"), flush=True)


def serve(host: str | None = None, port: int | None = None) -> None:
    os.environ.setdefault("SIBYL_MEMORY_TELEMETRY", "0")     # Sibyl's heartbeat is off on this server (its documented opt-out)
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = port or int(os.environ.get("PORT", "8080"))
    state = State()
    _restore_projects()                    # before serving: the projects kept on devnet, when this disk has none
    threading.Thread(target=lambda: preorder.preflight_status(force=True), daemon=True).start()   # the money path, simulated
    threading.Thread(target=tasks.available, daemon=True).start()        # seeds the demo round when no round is open
    valley.start_sweeper()                 # missed milestone deadlines: refund + reopen, every KNOS_VALLEY_SWEEP_S seconds
    front.start(state)                     # the seeded research products (a wiped disk never shows an empty app)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    rest_ok, rest_why = state.rest.ready()
    print(f"Knos demand check on http://{host}:{port}  Qloo REST: {'on' if rest_ok else 'off (' + rest_why + ')'}  "
          f"Qloo MCP: {state.q.mode} ({state.q.reason})  pre-orders on proof: preflight running (see /api/status)", flush=True)
    try:
        httpd.serve_forever()
    finally:
        state.q.close()
