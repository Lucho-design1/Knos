import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from knos_wanted import server
from knos_wanted.qloo import MOCK_LABEL, Qloo


@pytest.fixture
def app():
    state = server.State(Qloo())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", state
    httpd.shutdown()


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, raw if not r.headers.get("Content-Type", "").startswith("application/json") else json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_page_and_status(app):
    base, _ = app
    st, page = call(base, "/")
    assert st == 200 and b"Knos Wanted" in page and b"not a sales forecast" in page
    st, s = call(base, "/api/status")
    assert st == 200 and s["mode"] == "mock" and s["label"] == MOCK_LABEL and s["cluster"] == "devnet"
    st, _ = call(base, "/static/app.js")
    assert st == 200
    assert call(base, "/static/../server.py")[0] == 404


def test_report_endpoint_and_validation(app):
    base, state = app
    st, r = call(base, "/api/report", {"idea": "Vegan street food truck for students in Lagos", "rivals": "A, B"})
    assert st == 200 and r["label"] == MOCK_LABEL and state.known(r["hash"])
    assert [e["query"] for e in r["inputs"]["rivals"]] == ["A", "B"]
    assert call(base, "/api/report", {"idea": ""})[0] == 400
    assert call(base, "/api/preorder/demo", {"hash": "0" * 64})[0] in (400, 503)


def test_rate_limit(app, monkeypatch):
    base, _ = app
    monkeypatch.setitem(server.LIMITS, "report", (2, 600))
    codes = [call(base, "/api/report", {"idea": "Board game cafe in Paris"})[0] for _ in range(3)]
    assert codes == [200, 200, 429]
