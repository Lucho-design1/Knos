"""The Qloo trace (knos_wanted.trace) and the routes around it: a report's calls redacted with their limit, kept by id
after the report is gone, the "With and without Qloo" table only from the operator's key, and a check run with the
key unset says so."""
import json

from test_product_routes import app, call  # noqa: F401 - the fixture

from knos_wanted import trace


def test_a_trace_is_the_reports_calls_redacted_with_their_limit(app, monkeypatch, tmp_path):  # noqa: F811
    from knos_wanted import escrow
    base, state = app
    monkeypatch.setattr(escrow, "_state_dir", lambda: tmp_path)
    h = "d" * 64
    state.keep({"hash": h, "idea": "a recovery shoe", "label": "LIVE", "decision": {"verdict": "OPEN", "reasons": ["r"]},
                "calls": [{"n": 1, "call": "GET /search", "what": "closest products", "params": {"query": "recovery shoe", "types": "urn:entity:brand"},
                           "at": "t", "body_digest": "3 results: Hoka", "effect": "leader"}]})
    st, t = call(base, f"/api/trace?hash={h}")
    assert st == 200 and t["calls"][0]["endpoint"] == "GET /search" and t["calls"][0]["params"]["types"] == "urn:entity:brand"
    assert t["calls"][0]["excerpt"] == "3 results: Hoka" and "not a statement about any one person" in t["limit"]
    assert "key" not in json.dumps(t).lower().replace("monkey", "")                      # no credential in a trace
    assert call(base, "/api/trace/keep", {"hash": h})[1]["kept"] is True
    with state.lock:
        state.reports.pop(h)
    assert call(base, f"/api/trace?hash={h}")[0] == 200                                   # the kept copy, after the report is gone
    assert call(base, f"/api/trace?hash={'e' * 64}")[0] == 404 and call(base, "/api/trace/keep", {"hash": "e" * 64})[0] == 400
    assert call(base, "/trace.html")[0] == 200 and call(base, "/with-without")[0] == 200


def test_the_with_and_without_table_is_published_only_with_the_operators_key(app, monkeypatch, tmp_path):  # noqa: F811
    from knos_wanted import escrow
    base, _ = app
    monkeypatch.setattr(escrow, "_state_dir", lambda: tmp_path)
    monkeypatch.setenv("KNOS_ADMIN_KEY", "k" * 40)
    rows = [{"field": "food", "idea": "x", "with": {"hash": "a" * 64}, "without": {"hash": "b" * 64}, "changed": ["verdict"]}]
    assert call(base, "/api/qloo-diff")[0] == 404
    assert call(base, "/api/qloo-diff", {"rows": rows})[0] == 401
    import urllib.request
    req = urllib.request.Request(base + "/api/qloo-diff", json.dumps({"rows": rows, "summary": {"changed": 1}}).encode(),
                                 {"Content-Type": "application/json", "X-Knos-Admin": "k" * 40})
    with urllib.request.urlopen(req, timeout=30) as r:
        assert json.loads(r.read())["published"] == 1
    assert call(base, "/api/qloo-diff")[1]["rows"][0]["changed"] == ["verdict"]


def test_a_check_with_the_key_unset_says_so(app):  # noqa: F811
    base, _ = app
    st, rep = call(base, "/api/check", {"idea": "a plant-based burger chain", "without_qloo": True})
    assert st == 200 and rep["without_qloo"] is True and rep["decision"]["verdict"] == "CANNOT_DECIDE" and not rep["calls"]
    assert trace.build(rep)["without_qloo"] is True
