"""The agent's live crossing, its memory (Sibyl), MCP over HTTP, the Blink, sign-in providers, factoring and the price
tier, on SYNTHETIC fixtures (no network, no chain)."""
import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_check import IDEA, FakeQloo

from knos_wanted import agent, auth, blink, check, research, server
from knos_wanted.qloo_mcp import InProcess, Qloo

CARD = {"hash": "c" * 64, "title": "A synthetic landmark paper", "year": 2016, "cited_by_count": 5000, "retraction": {"retracted": False},
        "nobel": None, "proven_result": {"quote": "We present a sensor.", "source": "https://doi.org/10.0/x"}, "topics": ["Sweat"],
        "product": IDEA, "product_source": "synthetic", "field": "Engineering", "topic": "Wearables", "ids": {"doi": "10.0/x"}}


@pytest.fixture
def st(monkeypatch):
    s = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None), FakeQloo())
    monkeypatch.setattr(research, "research_card", lambda ref, product=None, **k: {**CARD, "product": product or CARD["product"]})
    return s


def test_the_crossing_streams_steps_sets_the_plan_and_remembers(st):
    job = agent.start(st, ref="10.0/x", place="Lagos", wait=True)
    assert job["status"] == "done", job.get("error")
    kinds = [s["kind"] for s in job["steps"]]
    assert kinds[0] == "memory" and "paper" in kinds and kinds.count("qloo") >= 8 and "decision" in kinds
    q = [s for s in job["steps"] if s["kind"] == "qloo"]
    assert all(s["tool"].startswith("GET /") and s["effect"] and s["output"] for s in q)          # every Qloo step: call, output, effect
    assert any(s["title"].startswith("launch cities") for s in q) and any("semantic" in s["title"] for s in q)
    rep = st.report(job["report"])
    plan = rep["decision"]["plan"]
    assert plan["tier"] in ("budget", "mid", "premium") and plan["unit_price"] in (1, 2, 4) and plan["where"] and plan["who"]["age"]
    assert plan["escrow_target"] == plan["target_units"] * plan["unit_price"]
    titles = [s["title"] for s in job["steps"]]
    assert "WHO: the target audience" in titles and "PRICE: the tier" in titles and "ESCROW: target and reserve" in titles
    again = agent.start(st, ref="10.0/x", place="Lagos", wait=True)                 # Sibyl: the agent's memory of this paper
    assert again["steps"][0]["title"] == "the agent remembers this paper" and "decision OPEN" in again["steps"][0]["output"]


def test_price_tier_from_spending_segments():
    seg = lambda n, a: {"name": n + " (Spending Habits)", "affinity": a, "src": 3}   # noqa: E731
    assert check.price_tier([seg("Gourmand Fine Dining", 0.8), seg("Discount Shoppers", 0.5)])["tier"] == "premium"
    assert check.price_tier([seg("Discount Shoppers", 0.8)])["tier"] == "budget"
    assert check.price_tier([seg("Yoga", 0.9)]) == {"tier": "mid", "unit_price": 2, "score": 0.0, "segments_seen": [], "src": 3}


@pytest.fixture
def http(st):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(st))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", st
    httpd.shutdown()


def post(base, path, body, headers=None):
    req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def test_mcp_over_http_lists_and_calls(http):
    base, _ = http
    c, init, _ = post(base, "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert c == 200 and init["result"]["protocolVersion"] and init["result"]["capabilities"]["tools"]
    assert post(base, "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})[0] == 202
    c, lst, _ = post(base, "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in lst["result"]["tools"]] == ["knos_cross", "knos_research_card", "knos_demand_check"]
    c, x, _ = post(base, "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "knos_cross", "arguments": {"ref": "10.0/x"}}})
    sc = x["result"]["structuredContent"]
    assert sc["status"] == "done" and sc["decision"]["verdict"] == "OPEN" and len(sc["steps"]) > 10
    assert get(base, "/mcp")[0] == 405


def test_the_live_crossing_over_the_web_api(http):
    base, st = http
    c, j, _ = post(base, "/api/cross", {"ref": "10.0/x"})
    assert c == 200 and j["id"]
    for _ in range(100):
        c, p, _ = get(base, f"/api/cross?id={j['id']}&since=0")
        if p["status"] != "running":
            break
        import time
        time.sleep(0.1)
    assert p["status"] == "done" and p["total"] == len(p["steps"]) and p["report"]


def test_the_blink(http):
    base, st = http
    job = agent.start(st, ref="10.0/x", wait=True)
    c, rules, h = get(base, "/actions.json")
    assert c == 200 and rules["rules"][0]["pathPattern"] == "/api/actions/**" and h["Access-Control-Allow-Origin"] == "*"
    c, a, h = get(base, f"/api/actions/preorder?report={job['report']}")
    assert c == 200 and a["type"] == "action" and a["links"]["actions"][0]["href"].endswith("&units=5") and h["X-Action-Version"]
    assert "set by Qloo" in a["description"] and h["X-Blockchain-Ids"].startswith("solana:")
    c, e, _ = post(base, f"/api/actions/preorder?report={job['report']}&units=5", {"account": "So11111111111111111111111111111111111111112"})
    assert c == 400 and "escrow unavailable" in e["message"]                          # no escrow keys in tests: refused plainly


def test_sign_in_providers_switch_on_with_their_keys(monkeypatch):
    for k in ("GOOGLE_CLIENT_ID", "ORCID_CLIENT_ID", "ORCID_CLIENT_SECRET", "RESEND_API_KEY", "KNOS_WANTED_EMAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    cfg = auth.config()
    assert cfg["google_client_id"] is None and cfg["orcid"] is False and cfg["email_provider"] is False
    with pytest.raises(auth.AuthError, match="ORCID sign-in is not configured"):
        auth.orcid_authorize("https://knos.example/auth/orcid/callback")
    monkeypatch.setenv("ORCID_CLIENT_ID", "APP-X")
    monkeypatch.setenv("ORCID_CLIENT_SECRET", "s")
    url = auth.orcid_authorize("https://knos.example/auth/orcid/callback")
    assert url.startswith("https://orcid.org/oauth/authorize?") and "scope=%2Fauthenticate" in url
    state = url.split("state=")[1]
    ok = lambda req, timeout=None: io.BytesIO(json.dumps({"orcid": "0000-0002-1825-0097", "name": "Josiah Carberry"}).encode())  # noqa: E731
    s = auth.orcid_callback("code", state, "https://knos.example/auth/orcid/callback", opener=ok)
    assert s["sub"] == "orcid:0000-0002-1825-0097" and s["kind"] == "orcid"
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("KNOS_WANTED_EMAIL_FROM", "Knos <signin@knos.example>")
    sent = {}

    def mail(req, timeout=None):
        sent["body"] = json.loads(req.data)
        return io.BytesIO(b"{}")
    assert auth.email_link("ada@example.com", "https://knos.example", opener=mail)["sent"]
    tok = sent["body"]["text"].split("#magic=")[1].split()[0]
    assert auth.email_verify(tok)["label"] == "ada@example.com"
    with pytest.raises(auth.AuthError, match="already used"):
        auth.email_verify(tok)
    assert auth.config()["orcid"] and auth.config()["email_provider"]


def test_factoring_reports_what_the_program_says(monkeypatch, tmp_path):
    from knos_wanted import preorder
    from knos import chain
    rec = {"order": "So11111111111111111111111111111111111111112", "units": 10, "unit_price": 2,
           "maker_wallet": "4dFAUoXNDbmPCJ1CPCFyaJqLW5WWY3i2TE3VKEdSbC31", "doc": {"payee": {"payee_id": 10 ** 15 + 7}},
           "report": "b" * 64, "claim_id": "knos-idea:" + "0" * 32}
    from solders.keypair import Keypair
    monkeypatch.setenv("KNOS_WANTED_DEVNET_KEYPAIR", json.dumps(list(bytes(Keypair()))))

    class Led:
        url = "https://api.devnet.solana.com"
    monkeypatch.setattr(chain, "call", lambda url, m, p, timeout=10: {"value": {"err": {"InstructionError": [0, {"Custom": 88}]}}})
    out = blink.factor(rec, 500, led=Led())
    assert out["status"] == "SIMULATED (off-program)" and out["assign_simulation"]["custom_code"] == 88
    assert out["advance"] == 19.0 and out["face_value"] == 20 and "no assignment exists on chain" in out["note"]
    assert preorder.load(rec["order"])["factoring"]["status"].startswith("SIMULATED")
    monkeypatch.setattr(chain, "call", lambda url, m, p, timeout=10: {"value": {"err": None}})
    assert blink.factor(rec, 500, led=Led())["status"] == "ready"

