"""Knos Gate as a GitHub App: a small webhook server (standard library HTTP, `cryptography` for the App's JWT).

NOT REGISTERED. docs/reference/PR_GATE.md ("Register the App") lists the founder's steps. Once registered:

    export KNOS_APP_ID=<the App's id>
    export KNOS_APP_KEY_FILE=/path/to/the-app.private-key.pem      # never committed
    export KNOS_APP_WEBHOOK_SECRET_FILE=/path/to/webhook-secret      # never committed
    python github-app/server.py --port 8787

Every request must carry a valid X-Hub-Signature-256; anything else is answered 401 and not read further. The logic
is knos.gate.app.handle (tested in tests/test_gate_app.py); this file only wires HTTP to it."""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from knos.gate import app  # noqa: E402
from knos.gate.github import http  # noqa: E402

MAX_BODY = 25 * 1024 * 1024


def _config() -> tuple[str, bytes, bytes]:
    app_id = os.environ["KNOS_APP_ID"]
    key = Path(os.environ["KNOS_APP_KEY_FILE"]).read_bytes()
    secret = Path(os.environ["KNOS_APP_WEBHOOK_SECRET_FILE"]).read_bytes().strip()
    return app_id, key, secret


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server's name
        if self.path != "/webhook":
            return self._say(404, "not found")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._say(413, "body size")
        body = self.rfile.read(n)
        app_id, key, secret = _config()
        if not app.verify_signature(secret, body, self.headers.get("X-Hub-Signature-256")):
            return self._say(401, "bad signature")
        event = self.headers.get("X-GitHub-Event", "")
        payload = json.loads(body)
        inst = (payload.get("installation") or {}).get("id")
        if not inst:
            return self._say(202, "no installation")
        jwt = app.app_jwt(app_id, key)
        token = app.installation_token(jwt, inst, http(jwt))
        done = app.handle(event, payload, http(token), token=token)
        return self._say(200, "; ".join(done))

    def do_GET(self):  # noqa: N802
        return self._say(200, "knos gate") if self.path == "/health" else self._say(404, "not found")

    def _say(self, code: int, text: str):
        raw = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):  # one line per request, no headers, no body
        sys.stderr.write("%s %s\n" % (self.command, fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(description="Knos Gate GitHub App webhook server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--manifest", action="store_true", help="print the App manifest and exit")
    a = ap.parse_args()
    if a.manifest:
        print(json.dumps(app.MANIFEST, indent=2))
        return 0
    _config()       # fail now, not at the first webhook
    ThreadingHTTPServer((a.host, a.port), Hook).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
