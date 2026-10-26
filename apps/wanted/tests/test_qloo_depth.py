"""Qloo, used to its depth: a request with a parameter Qloo's docs do not document is refused and nothing is sent;
/status/qloo says the last answer Qloo gave this server without asking it anything; the published table of what
each Qloo signal changes is the one its JSON holds. SYNTHETIC answers only."""
import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from knos_wanted import qloo_guard, qloo_rest, server
from knos_wanted.qloo_mcp import InProcess, Qloo
from knos_wanted.qloo_rest import Client, QlooError

ROOT = Path(__file__).resolve().parents[3]


class Opener:
    def __init__(self):
        self.n = 0

    def __call__(self, req, timeout=None):
        self.n += 1
        return io.BytesIO(json.dumps({"results": {"entities": []}}).encode())


def _client(tmp_path, op):
    return Client(key="test-key-not-real", base="https://example.test", folder=tmp_path, budget=100, opener=op, bucket=qloo_rest._Bucket(1000.0))


def test_an_undocumented_parameter_is_refused_and_nothing_is_sent(tmp_path):
    op = Opener()
    with pytest.raises(QlooError, match="not documented for filter.type=urn:entity:brand"):
        _client(tmp_path, op).get("/v2/insights", {"filter.type": "urn:entity:brand", "signal.interests.entities": "x", "filter.made_up": "1"})
    with pytest.raises(QlooError, match="not a value docs.qloo.com lists"):
        _client(tmp_path, op).get("/v2/insights", {"filter.type": "urn:audience", "take": 5})
    with pytest.raises(QlooError, match="not documented for /search"):
        _client(tmp_path, op).get("/search", {"query": "tea", "filter.made_up": "1"})
    assert op.n == 0
    _client(tmp_path, op).get("/v2/insights", {"filter.type": "urn:entity:brand", "signal.interests.entities": "x", "take": 5})
    assert op.n == 1                                        # a documented request goes


def test_the_documented_use_cases_pass():
    for path, p in [("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": "x"}),
                    ("/v2/insights", {"filter.type": "urn:tag", "signal.interests.entities": "x", "diversify.by": "subtype", "take": 8}),
                    ("/v2/insights", {"filter.type": "urn:heatmap", "filter.location.query": "NYC", "signal.interests.entities": "x", "take": 5}),
                    ("/v2/analysis/compare", {"a.signal.interests.entities": "x", "b.signal.interests.entities": "y", "take": 30})]:
        assert qloo_guard.problems(path, p) == [], (path, p)


def test_status_qloo_says_the_last_answer_and_asks_qloo_nothing(monkeypatch):
    monkeypatch.setattr(qloo_rest, "LAST", {"at": "2026-10-26T08:14:45Z", "status": 429, "path": "/search"})
    sent = []
    monkeypatch.setattr(qloo_rest.Client, "_get", lambda self, *a, **k: sent.append(a))
    st = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None), _client(Path("."), Opener()))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(st))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/status/qloo", timeout=10) as r:
            page = r.read().decode()
        assert r.status == 200 and "HTTP 429" in page and "2026-10-26T08:14:45Z" in page and sent == []
    finally:
        httpd.shutdown()


def test_the_published_ablation_table_is_its_json():
    doc = json.loads((ROOT / "docs" / "reference" / "qloo_ablation.json").read_text(encoding="utf-8"))
    page = (ROOT / "web" / "how-we-test.html").read_text(encoding="utf-8")
    sec = page.split("<!-- ablation:start -->")[1].split("<!-- ablation:end -->")[0]
    assert doc["samples"] == 6 and sec.count("<tr><td>") == len(doc["rows"]) and "What each Qloo signal changes" in sec
    assert all(set(r) == {"chip", "removed", "city", "target", "label"} for r in doc["rows"])          # derived values only
