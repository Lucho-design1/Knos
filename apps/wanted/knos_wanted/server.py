"""Knos's demand check as one service: a static page + a small JSON API, Python standard library only. Qloo is
reached ONLY from this server: its REST API (knos_wanted.qloo_rest, the primary path: POST /api/check) and, for the
older confirm-each-match flow, `qloo mcp` (knos_wanted.qloo_mcp). The browser never sees a key or calls Qloo.

    python -m knos_wanted serve            (HOST, default 127.0.0.1; PORT, default 8080)

POST /api/check {idea, place?, leader?}            the report and the code-made decision (no sign-in needed)
POST /api/preorder {report, units, maker_wallet?}  lock test units for the maker, paid only on proof (signed in)
POST /api/milestone {commitment, evidence_url}     verify the evidence; 2 of 3 referees sign PASS; release (signed in)
POST /api/refund {commitment}                      past the deadline: back to the buyer (signed in)
Rate limits per client address keep a public demo from draining the Qloo quota and the devnet test wallet.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import auth, buyer, catalog, check, company, demand, escrow, planner, preorder, privacy
from .qloo_mcp import AGGREGATE, Qloo, QlooUnavailable
from .qloo_rest import Client

STATIC = Path(__file__).parent / "static"
MAX_BODY = 16_384
SESSION_S = 30 * 60
LIMITS = {"maker": (20, 600), "search": (40, 600), "buyer": (20, 600), "publish": (10, 600), "demo": (4, 600),
          "faucet": (2, 3600), "tx": (20, 600), "check": (12, 600), "lock": (6, 600), "auth": (30, 600),
          "milestone": (30, 600), "milestone_one": (10, 3600)}   # (calls, seconds) per client
GLOBAL_DEMO = (60, 3600)                                           # demo pre-orders, all clients
ROUTES = {"/api/maker/start": "maker", "/api/maker/search": "search", "/api/maker/confirm": "maker", "/api/maker/publish": "publish",
          "/api/buyer/start": "buyer", "/api/buyer/confirm": "buyer", "/api/preorder/demo": "demo", "/api/preorder/faucet": "faucet",
          "/api/preorder/tx": "tx", "/api/preorder/submit": "tx",
          "/api/check": "check", "/api/preorder": "lock", "/api/milestone": "milestone", "/api/refund": "lock",
          "/api/auth/challenge": "auth", "/api/auth/passkey/register": "auth", "/api/auth/passkey/login": "auth",
          "/api/auth/google": "auth", "/api/auth/guest": "auth"}
SIGNED_IN = ("/api/preorder", "/api/milestone", "/api/refund")


class State:
    def __init__(self, q: Qloo | None = None, rest: Client | None = None):
        self.q = q or Qloo()
        self.rest = rest or Client()
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
            fwd = self.headers.get("X-Forwarded-For", "") if os.environ.get("KNOS_WANTED_TRUST_PROXY") == "1" else ""
            return (fwd.split(",")[0].strip() or self.client_address[0])[:64]

        def _send(self, code: int, body, ctype: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(code)
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

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
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
                    return self._send(200, preorder.public(preorder.load((qs.get("id") or [""])[0])))
                except ValueError as why:
                    return self._send(404, {"error": str(why)})
            if u.path == "/api/auth/config":
                return self._send(200, auth.config())
            if u.path == "/api/fees":
                return self._send(200, preorder.fee_line())
            return self._send(404, {"error": "not found"})

        def status(self) -> dict:
            ok, why = preorder.ready()
            rest = state.rest.status()
            mcp = state.q.status()
            if rest["rest"]:        # the decision path is Qloo's REST API: when it is live, the server is live
                top = {"mode": "live", "label": check.LIVE_LABEL, "reason": "Qloo REST API key configured on this server",
                       "mcp_flow": {k: mcp.get(k) for k in ("mode", "label", "reason")}}
            else:
                top = {"no_key_behaviour": "every check answers CANNOT_DECIDE (" + check.NO_EVIDENCE + "); pre-orders never open"}
            return {**mcp, **top, "qloo_rest": rest, "preorders": {"available": ok, "why": why},
                    "fees": preorder.fee_line(), "auth": auth.config(),
                    "framing": demand.FRAMING, "escrow": escrow.available(),
                    "demo_wallet": bool(os.environ.get("KNOS_WANTED_DEVNET_KEYPAIR")), "cluster": "devnet",
                    "record": company.root() is not None, "targets": ["brand", "place", "artist", "movie", "book", "podcast", "tv_show"]}

        def do_POST(self):
            u = urlparse(self.path)
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
                if u.path.startswith("/api/auth/") or u.path in ("/api/check",) + SIGNED_IN:
                    return self._send(200, self.route_v2(u.path, body))
                return self._send(200, self.route(u.path, body))
            except auth.AuthError as why:
                return self._send(401, {"error": str(why)[:300]})
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
            except Exception as why:  # noqa: BLE001 - chain/RPC errors: say what, never a key
                return self._send(502, {"error": f"{type(why).__name__}: {str(why)[:300]}"})

        def _origin(self) -> tuple[str, str]:
            host = (self.headers.get("Host") or "").split(":")[0]
            rp_id = os.environ.get("KNOS_WANTED_RP_ID") or host
            origin = self.headers.get("Origin") or ""
            o = urlparse(origin)
            if o.hostname != rp_id or (o.scheme != "https" and rp_id not in ("localhost", "127.0.0.1")):
                raise auth.AuthError("passkeys work only on this site's own https origin (or localhost)")
            return origin, rp_id

        def route_v2(self, path: str, body: dict) -> dict:
            """Knos's demand check on Qloo's REST API, pre-orders paid on proof, and sign-in."""
            if path == "/api/check":
                idea = body.get("idea")
                if not isinstance(idea, str) or not idea.strip():
                    raise ValueError("describe the idea")
                privacy.check({"idea": idea, "place": body.get("place"), "leader": body.get("leader")})
                ex = body.get("exclude") or []
                if not isinstance(ex, list) or len(ex) > 20 or not all(isinstance(x, str) and len(x) < 80 for x in ex):
                    raise ValueError("exclude: a list of up to 20 Qloo entity ids the maker unticked")
                rep = check.demand_check(idea, _text(body.get("place")), _text(body.get("leader"), 80), client=state.rest, exclude=ex)
                rep["fees"] = preorder.fee_line()
                state.keep_check(rep)
                return rep
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
            user = self.user or {}
            if path == "/api/preorder":
                rep = state.report(body.get("report") or body.get("hash"))
                if rep is None or rep.get("kind") != check.KIND:
                    raise ValueError("unknown report: run the demand check first")
                return preorder.lock(rep, body.get("units", 5), f"{user.get('kind')}: {user.get('label')}", _text(body.get("maker_wallet"), 44))
            rec = preorder.load(str(body.get("commitment", "")))
            if path == "/api/milestone":
                return preorder.milestone(state.report(rec["report"]) or {}, rec["order"], str(body.get("evidence_url", "")))
            return preorder.refund(rec["order"])

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
                res = escrow.demo_preorder(h, units)
            else:
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


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = port or int(os.environ.get("PORT", "8080"))
    state = State()
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    rest_ok, rest_why = state.rest.ready()
    print(f"Knos demand check on http://{host}:{port}  Qloo REST: {'on' if rest_ok else 'off (' + rest_why + ')'}  "
          f"Qloo MCP: {state.q.mode} ({state.q.reason})  pre-orders on proof: {preorder.ready()[1]}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        state.q.close()
