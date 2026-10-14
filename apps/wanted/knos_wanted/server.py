"""Knos's demand check as one service: a static page + a small JSON API, Python standard library only. Qloo is
reached ONLY from this server, through `qloo mcp` (knos_wanted.qloo_mcp); the browser never sees a key or calls Qloo.

    python -m knos_wanted serve            (HOST, default 127.0.0.1; PORT, default 8080)

No login. Rate limits per client address keep a public demo from draining the Qloo quota and the devnet test wallet.
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

from . import buyer, catalog, company, demand, escrow, planner, privacy
from .qloo_mcp import AGGREGATE, Qloo, QlooUnavailable

STATIC = Path(__file__).parent / "static"
MAX_BODY = 16_384
SESSION_S = 30 * 60
LIMITS = {"maker": (20, 600), "search": (40, 600), "buyer": (20, 600), "publish": (10, 600), "demo": (4, 600),
          "faucet": (2, 3600), "tx": (20, 600)}                    # (calls, seconds) per client
GLOBAL_DEMO = (60, 3600)                                           # demo pre-orders, all clients
ROUTES = {"/api/maker/start": "maker", "/api/maker/search": "search", "/api/maker/confirm": "maker", "/api/maker/publish": "publish",
          "/api/buyer/start": "buyer", "/api/buyer/confirm": "buyer", "/api/preorder/demo": "demo", "/api/preorder/faucet": "faucet",
          "/api/preorder/tx": "tx", "/api/preorder/submit": "tx"}


class State:
    def __init__(self, q: Qloo | None = None):
        self.q = q or Qloo()
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
            return self.reports.get(h) if isinstance(h, str) else None

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
            return self._send(404, {"error": "not found"})

        def status(self) -> dict:
            return {**state.q.status(), "framing": demand.FRAMING, "escrow": escrow.available(),
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
                return self._send(200, self.route(u.path, body))
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
    print(f"Knos demand check on http://{host}:{port}  Qloo: {state.q.mode} ({state.q.reason})  escrow: {'on' if escrow.available() else 'off'}")
    try:
        httpd.serve_forever()
    finally:
        state.q.close()
