"""M4 test_qloo_safe_use: the Qloo hackathon kit's SAFE_USE and API_ACCESS rules, kept in code. Network is a fake
opener answering SYNTHETIC bodies (not Qloo data); every rule on /qloo-safe-use names a test that checks it."""
import json
import re
from pathlib import Path

import pytest
from test_product_routes import app, call  # noqa: F401 - the fixture
from test_qloo_rest import KEY, Opener, client

from knos_wanted import check, privacy, qloo_rest, trace

STATIC = Path(check.__file__).resolve().parent / "static"
PERSONAL = ["write to ada.lovelace@example.com", "call +1 512 555 0199", "my name is Ada Lovelace", "follow @ada_codes",
            "see https://ada.example.com", "ship to 12 Baker Street", "from 192.168.1.20", "device id A1B2"]
SENSITIVE = ["infer which customers have diabetes from their taste", "predict a voter's political party from the films they like",
             "guess people's income from their music", "identify a person's sexuality from their likes",
             "decide who gets a loan from their taste profile", "find out the religion of my neighbour from what she watches",
             "predict which people in Detroit will default on loans from their taste"]       # round 6 of the outside review


def test_the_refuse_list_comes_before_any_qloo_call():
    """Round 6: a demand check naming a word on the published list is refused before Qloo, like personal data."""
    from knos import refuse
    for cat, words in refuse.REFUSE.items():
        with pytest.raises(privacy.Refused, match="/api/refuse"):
            privacy.check({"idea": f"a product named for {words[0]}"})
    privacy.check({"idea": "a cordless glue gun for schools"})                  # an allowed look-alike


def test_words_in_any_alphabet_stay_whole():
    assert check.tokens("cómics para niños en el café") == ["cómics", "para", "niños", "en", "el", "café"]


@pytest.fixture
def counted(app, monkeypatch):  # noqa: F811
    base, state = app
    op = Opener()
    monkeypatch.setattr(state, "rest", client(Path(state.rest.folder) if hasattr(state.rest, "folder") else None, op))
    return base, state, op


def test_no_personal_field_and_no_inference_about_people_reaches_qloo(counted, tmp_path):
    base, state, op = counted
    for text in PERSONAL + SENSITIVE:                       # what every route runs before any Qloo call (privacy.check)
        assert privacy.problems({"idea": "a recovery shoe for runners " + text}), text
    for text in SENSITIVE:
        assert any("which Knos refuses" in p for p in privacy.problems({"idea": text})), text
    for text in (PERSONAL[0], SENSITIVE[0]):                 # and over HTTP, refused before Qloo
        st, got = call(base, "/api/check", {"idea": "a recovery shoe for runners " + text})
        assert st == 400 and got["error"].startswith("Knos sends no personal data to Qloo"), (text, got)
    st, got = call(base, "/api/check", {"idea": "a recovery shoe for runners", "near": "my name is Ada"})
    assert st == 400
    assert op.n == 0                                                                       # not one request reached Qloo


@pytest.mark.parametrize("code,said", [(401, "refused this server's API key"), (403, "refused this server's API key"),
                                       (429, "rate limit for this event key was reached")])
def test_a_bad_key_or_the_rate_limit_is_said_plainly_never_a_silent_fallback(tmp_path, monkeypatch, code, said):
    monkeypatch.setattr(qloo_rest.time, "sleep", lambda s: None)
    op = Opener(error=code)
    rep = check.demand_check("a plant-based burger chain", client=client(tmp_path, op))
    reasons = " ".join(rep["decision"]["reasons"])
    assert said in reasons and rep["label"] == "NO QLOO EVIDENCE" and rep["decision"]["verdict"] == "CANNOT_DECIDE", reasons
    assert all(r.full_url.startswith("https://example.test/") for r in op.reqs)            # one endpoint, no other credential


def test_retries_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(qloo_rest.time, "sleep", lambda s: None)
    op = Opener(error=429)
    with pytest.raises(qloo_rest.QlooError):
        client(tmp_path, op).get("/search", {"query": "burger", "take": 5})
    assert op.n == 2                                                                       # one try, one retry, then a clear error


def test_the_key_is_in_no_report_trace_or_error(tmp_path, monkeypatch):
    monkeypatch.setattr(qloo_rest.time, "sleep", lambda s: None)
    rep = check.demand_check("a plant-based burger chain", client=client(tmp_path, Opener({"results": {"entities": []}})))
    assert KEY not in json.dumps(rep) and KEY not in json.dumps(trace.build(rep))
    with pytest.raises(qloo_rest.QlooError) as e:
        client(tmp_path, Opener(error=401)).get("/search", {"query": "x", "take": 5})
    assert KEY not in str(e.value)
    for f in (STATIC / "app.js", STATIC / "demand_opts.js", STATIC / "valley.js"):
        assert "x-api-key" not in f.read_text(encoding="utf-8").lower()                   # the pages never hold or send a key


def test_other_sources_are_labelled_and_the_docs_mcp_is_never_called():
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'data-source="openalex"' in app_js and "not Qloo" in app_js
    pkg = Path(check.__file__).resolve().parent
    assert not any("docs.qloo.com/mcp" in f.read_text(encoding="utf-8") for f in pkg.rglob("*.py"))


def test_the_safe_use_page_maps_every_rule_of_the_kit():
    page = (STATIC / "qloo_safe_use.html").read_text(encoding="utf-8")
    rules = re.findall(r'<tr id="(r-[a-z]+)">', page)
    assert rules == ["r-infer", "r-personal", "r-source", "r-clarify", "r-untrusted", "r-explore", "r-secrets",
                     "r-credential", "r-errors", "r-small", "r-scrape", "r-surfaces", "r-docs"]
    tests = set(re.findall(r"<code>(test_[a-z_]+)</code>", page))
    here = Path(__file__).resolve().parent
    defined = {m for f in here.glob("test_*.py") for m in re.findall(r"(?m)^def (test_[a-z_]+)", f.read_text(encoding="utf-8"))}
    files = {f.stem for f in here.glob("test_*.py")}
    assert tests - {"test_provenance_ui"} <= defined | files, tests - defined - files      # each named test exists


def test_a_slow_heatmap_does_not_hold_up_the_verdict(tmp_path):
    """M7: a prefetched question that decides nothing is waited for only `wait_s`; then the report says it is left out,
    and a question that answers in time is read from the cache, not asked twice."""
    import io
    import time as _t

    class Slow(Opener):
        def __call__(self, req, timeout=None):
            self.n += 1
            if "urn%3Aheatmap" in req.full_url:
                _t.sleep(2.0)
            return io.BytesIO(json.dumps({"results": {"heatmap": [], "entities": []}}).encode())
    op = Slow()
    run = check._Run(client(tmp_path, op))
    heat = {"filter.type": "urn:heatmap", "filter.location.query": "Austin", "take": 5, "output.heatmap.boundary": "city"}
    quick = {"filter.type": "urn:demographics", "signal.interests.entities": "E1"}
    run.prefetch([("/v2/insights", heat), ("/v2/insights", quick)])
    t0 = _t.time()
    run.get("/v2/insights", quick, "who")
    body, n = run.get("/v2/insights", heat, "where: map points", wait_s=0.2)
    assert _t.time() - t0 < 1.5 and body is None and n is None and "had not answered" in run.calls[-1]["error"]
    assert op.n == 2                                                                       # each question asked once
