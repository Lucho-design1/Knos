import json
import urllib.parse

import pytest

from knos_wanted.qloo import MOCK_LABEL, Qloo, QlooError


def test_mock_without_key_is_labelled():
    q = Qloo()
    assert not q.live and q.mode == "mock"
    body = q.get("search", {"query": "coffee", "types": "urn:entity:brand"})
    assert body["_mock"] == MOCK_LABEL
    assert all("(synthetic)" in e["name"] and e["entity_id"].startswith("mock-") for e in body["results"])


def test_force_mock_ignores_key(monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "k")
    monkeypatch.setenv("KNOS_WANTED_MOCK", "1")
    assert Qloo().mode == "mock"


def test_live_uses_hackathon_base_and_header(fake, tmp_path):
    f = fake()
    q = Qloo(api_key="secret-key", opener=f, cache_dir=tmp_path / "c")
    body = q.get("insights", {"filter.type": "urn:entity:brand", "signal.interests.tags": ["urn:tag:a", "urn:tag:b"]})
    assert "_mock" not in body
    req = f.requests[0]
    u = urllib.parse.urlparse(req.full_url)
    assert f"{u.scheme}://{u.netloc}" == "https://hackathon.api.qloo.com" and u.path == "/v2/insights"
    qs = dict(urllib.parse.parse_qsl(u.query))
    assert qs["feature.explainability"] == "true" and qs["signal.interests.tags"] == "urn:tag:a,urn:tag:b"
    assert req.get_header("X-api-key") == "secret-key"
    assert "secret-key" not in req.full_url


def test_fixed_params_route_demographics_heatmap():
    q = Qloo(api_key="k")
    assert "filter.type=urn:demographics" in q.url("demographics", {})
    assert "filter.type=urn:heatmap" in q.url("heatmap", {"filter.location.query": "New York"})
    assert q.url("trending", {}).startswith("https://hackathon.api.qloo.com/v2/trending")
    assert q.url("compare", {}).startswith("https://hackathon.api.qloo.com/v2/analysis/compare")


def test_unserved_status_raises_and_cache_never_holds_key(fake, tmp_path):
    f = fake({"heatmap": 403})
    q = Qloo(api_key="secret-key", opener=f, cache_dir=tmp_path / "c")
    with pytest.raises(QlooError) as e:
        q.get("heatmap", {"filter.location.query": "NYC"})
    assert e.value.unserved and e.value.status == 403
    q.get("search", {"query": "x"})
    n = len(f.requests)
    q.get("search", {"query": "x"})          # served from the private server-side cache
    assert len(f.requests) == n
    files = list((tmp_path / "c").glob("*.json"))
    assert files and all("secret-key" not in p.read_text() for p in files)


def test_probe_file_marks_unserved(tmp_path):
    (tmp_path / "probe.json").write_text(json.dumps({"endpoints": {"compare": {"status": 403}, "search": {"status": 200}}}))
    q = Qloo(api_key="k", cache_dir=tmp_path / "qloo")
    assert q.unserved == {"compare"}
    with pytest.raises(QlooError):
        q.get("compare", {})
