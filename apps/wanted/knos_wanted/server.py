"""The one service: a static page + a small JSON API, Python standard library only.

    python -m knos_wanted serve            (HOST, default 127.0.0.1; PORT, default 8080)

No login. Rate limits per client address keep a public demo from draining the devnet test wallet.
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

from . import escrow, report
from .qloo import MOCK_LABEL, Qloo, QlooError

STATIC = Path(__file__).parent / "static"
MAX_BODY = 16_384
LIMITS = {"report": (20, 600), "demo": (4, 600), "faucet": (2, 3600), "tx": (20, 600)}   # (calls, seconds) per client
GLOBAL_DEMO = (60, 3600)                                                                 # demo pre-orders, all clients


class State:
    def __init__(self, q: Qloo | None = None):
        self.q = q or Qloo()
        self.reports: OrderedDict[str, dict] = OrderedDict()
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()

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

    def known(self, h: str) -> bool:
        with self.lock:
            return h in self.reports


def _names(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,;\n]", v)
    return [s.strip()[:60] for s in (v or []) if isinstance(s, str) and s.strip()][:3]


def make_handler(state: State):
    class H(BaseHTTPRequestHandler):
        server_version = "knos-wanted/0.1"

        def log_message(self, fmt, *args):  # no request logging: ideas are the visitor's, keys are never in URLs
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
            if u.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/static/"):
                f = (STATIC / u.path[len("/static/"):]).resolve()
                if STATIC.resolve() in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                return self._send(404, {"error": "not found"})
            if u.path == "/api/status":
                return self._send(200, self.status())
            if u.path == "/api/pool":
                h = (parse_qs(u.query).get("hash") or [""])[0]
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
            demo = bool(os.environ.get("KNOS_WANTED_DEVNET_KEYPAIR"))
            return {"mode": state.q.mode, "label": report.LIVE_LABEL if state.q.live else MOCK_LABEL, "framing": report.FRAMING,
                    "escrow": escrow.available(), "demo_wallet": demo, "cluster": "devnet",
                    "unserved": sorted(state.q.unserved)}

        def do_POST(self):
            u = urlparse(self.path)
            kind = {"/api/report": "report", "/api/preorder/demo": "demo", "/api/preorder/faucet": "faucet",
                    "/api/preorder/tx": "tx", "/api/preorder/submit": "tx"}.get(u.path)
            if kind is None:
                return self._send(404, {"error": "not found"})
            if not state.allow(self._client(), kind):
                return self._send(429, {"error": "too many requests from this address; try again in a few minutes"})
            try:
                body = self._json()
                if kind == "report":
                    idea = body.get("idea")
                    if not isinstance(idea, str) or not idea.strip():
                        raise ValueError("describe the idea")
                    loc = body.get("location") if isinstance(body.get("location"), str) and body["location"].strip() else None
                    r = report.build(idea, _names(body.get("rivals")), loc.strip()[:60] if loc else None, q=state.q)
                    state.keep(r)
                    return self._send(200, r)
                h = body.get("hash")
                if u.path != "/api/preorder/faucet" and u.path != "/api/preorder/submit" and not state.known(h):
                    raise ValueError("unknown report: build the report first")
                units = body.get("units", 5)
                if u.path == "/api/preorder/demo":
                    return self._send(200, escrow.demo_preorder(h, units))
                if u.path == "/api/preorder/faucet":
                    return self._send(200, escrow.faucet(str(body.get("owner", ""))))
                if u.path == "/api/preorder/tx":
                    return self._send(200, escrow.wallet_tx(h, str(body.get("owner", "")), units))
                return self._send(200, escrow.submit(str(body.get("transaction", "")), str(body.get("owner", ""))))
            except escrow.EscrowUnavailable as why:
                return self._send(503, {"error": str(why)})
            except QlooError as why:
                return self._send(502, {"error": f"Qloo: {why.why}"})
            except (ValueError, TypeError, KeyError) as why:
                return self._send(400, {"error": str(why)[:300]})
            except Exception as why:  # noqa: BLE001 - chain/RPC errors: say what, never a key
                return self._send(502, {"error": f"{type(why).__name__}: {str(why)[:300]}"})

    return H


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = port or int(os.environ.get("PORT", "8080"))
    state = State()
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"knos-wanted on http://{host}:{port}  Qloo: {state.q.mode}  escrow: {'on' if escrow.available() else 'off'}")
    httpd.serve_forever()
