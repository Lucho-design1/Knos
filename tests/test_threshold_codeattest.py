"""The code referee's attestation (knos.threshold.codeattest): the verdict file host 2 writes from its own check, the
GitHub OIDC token whose audience names that verdict verified ON CHAIN by knos_oidc (its test build in LiteSVM, through
the same relay.verify_only the app server calls), the Sigstore bundle checked against Sigstore's trust root (a REAL
public bundle, offline), the app server's /api/referee/attest, the PC daemon's healthz pings and the workflow's shape.

The tokens here are signed by the tests' seed key (tests/_settle.py), which the TEST build of knos_oidc trusts as a
genesis key; GitHub signs the real ones. The Sigstore bundle is a real one, GitHub CLI 2.102.0's build provenance
(tests/thirdparty/sigstore_cli_gh_2.102.0_provenance.json.sn, as GitHub's attestation API stores it, snappy), because no
test can mint a Fulcio certificate.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from knos.threshold import codeattest as CA
from knos.threshold import ghoidc, participant, session

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
CLI_BUNDLE = Path(__file__).parent / "thirdparty" / "sigstore_cli_gh_2.102.0_provenance.json.sn"
CLI_SHA = "bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386"      # gh_2.102.0_linux_amd64.tar.gz (its checksums file)
CLI_ID = "https://github.com/cli/cli/.github/workflows/deployment.yml@refs/heads/trunk"
CLI_COMMIT = "fc4b137cdef0a6bd28fd461b7cf9c84a5812a8cd"
RUN_SHA = "e" * 40
ENV = {"GITHUB_REPOSITORY": "drexthealpha/Knos", "GITHUB_WORKFLOW_REF": "drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main",
       "GITHUB_SHA": RUN_SHA, "GITHUB_RUN_ID": "39128205037", "GITHUB_RUN_ATTEMPT": "1"}


def _session(sid="ab" * 16, digest=b"\x11" * 32):
    doc = {"orders": {"stage1": {"order": "Ord1111111111111111111111111111111111111111"}}, "program": "FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4",
           "claim": {"id": "knos-claim-1"}}
    return {"id": sid, "state": "round1", "digest": digest.hex(), "group_key": "CZ599fmDD6ATkRsbUbdZiAQE7uF9sJrGFmJ6k54ujb4E",
            "request": {"kind": "knos-milestone-release", "doc": doc, "stage": "stage1", "evidence_url": "https://example.org/ev"}}


def _verdict(s=None):
    s = s or _session()
    return CA.canonical(CA.verdict(s, bytes.fromhex(s["digest"]), {"page_sha256": "f" * 64, "evidence_hash": "d" * 64}, ENV))


# -- the verdict file -------------------------------------------------------------------------------------------------
def test_the_verdict_names_the_digest_the_group_signs_and_the_run_that_checked_it(tmp_path):
    s = _session()
    raw = _verdict(s)
    rec, sha = CA.check_verdict(raw, s)
    assert sha == hashlib.sha256(raw).hexdigest() and rec["digest"] == s["digest"] and rec["github"]["sha"] == RUN_SHA
    assert CA.audience(raw) == "knos-referee:verdict:" + sha and len(CA.audience(raw)) < 100
    assert CA.run_url(rec) == "https://github.com/drexthealpha/Knos/actions/runs/39128205037/attempts/1"
    f = CA.write(rec, tmp_path)
    assert f.read_bytes() == raw and f.name == f"verdict-{s['id']}.json"
    # another session's digest, a spaced copy, another workflow, a FAIL: refused
    with pytest.raises(CA.AttestError, match="not this session"):
        CA.check_verdict(raw, {**s, "digest": "22" * 32})
    with pytest.raises(CA.AttestError, match="canonical"):
        CA.check_verdict(json.dumps(json.loads(raw), indent=1), s)
    other = CA.canonical({**rec, "github": {**rec["github"], "workflow_ref": "drexthealpha/Knos/.github/workflows/x.yml@refs/heads/main"}})
    with pytest.raises(CA.AttestError, match="referee.yml"):
        CA.check_verdict(other, s)
    with pytest.raises(CA.AttestError, match="PASS"):
        CA.check_verdict(CA.canonical({**rec, "verdict": "FAIL"}), s)


def test_host_2_writes_a_verdict_only_for_a_digest_its_own_check_recomputed(monkeypatch, tmp_path):
    s = _session()
    seen = []

    class Client:
        def session(self, sid):
            return {**s, "state": "round2"}           # the signers are fixed: no FROST round is needed for this test

    monkeypatch.setattr(participant, "milestone_digest", lambda req, gk, led, **kw: (bytes.fromhex(s["digest"]), {"page_sha256": "f" * 64, "evidence_hash": "d" * 64}))
    share = {"id": 2, "group_key": s["group_key"]}
    got = participant.sign_session(share, Client(), s["id"], None, on_verdict=lambda ss, d, ev: seen.append(CA.write(CA.verdict(ss, d, ev, ENV), tmp_path)))
    assert got["outcome"].startswith("not chosen") and len(seen) == 1 and CA.check_verdict(seen[0].read_bytes(), s)[0]["session"] == s["id"]
    monkeypatch.setattr(participant, "milestone_digest", lambda req, gk, led, **kw: (b"\x99" * 32, {}))
    got = participant.sign_session(share, Client(), s["id"], None, on_verdict=lambda *a: seen.append(a))
    assert got["outcome"].startswith("refused") and len(seen) == 1      # another digest: no verdict, nothing signed


# -- snappy and Sigstore ------------------------------------------------------------------------------------------------
def test_snappy_blocks_decode_literals_and_copies_and_refuse_a_bad_one():
    assert CA.unsnappy(bytes([8, 3 << 2]) + b"abcd" + bytes([0x01, 4])) == b"abcdabcd"      # literal 4, copy-1 len 4 off 4
    assert CA.unsnappy(bytes([6, 1 << 2]) + b"ab" + bytes([(3 << 2) | 2, 2, 0])) == b"ababab"  # copy-2 len 4 off 2
    for bad in (bytes([5, 3 << 2]) + b"abcd", bytes([8, 3 << 2]) + b"abcd" + bytes([0x01, 9]), b"\xff\xff\xff\xff\xff\xff"):
        with pytest.raises(CA.AttestError):
            CA.unsnappy(bad)


def test_a_real_sigstore_bundle_verifies_against_sigstores_trust_root_and_nothing_else_does():
    raw = CA.unsnappy(CLI_BUNDLE.read_bytes())
    got = CA.verify_bundle(raw, CLI_SHA, identity=CLI_ID, commit=CLI_COMMIT)
    assert got["ok"] and got["commit"] == CLI_COMMIT and got["invocation"].startswith("https://github.com/cli/cli/actions/runs/")
    assert got["checked_by"] == "knos.sources.sigstore" and got["log_index"] == 3010358693 and CA.rekor_url(got["log_index"]).endswith("=3010358693")
    with pytest.raises(CA.AttestError, match="subjects"):
        CA.verify_bundle(raw, "0" * 64, identity=CLI_ID)                    # another artifact
    with pytest.raises(CA.AttestError, match="does not verify"):
        CA.verify_bundle(raw, CLI_SHA)                                     # Knos's referee identity: not this certificate
    with pytest.raises(CA.AttestError, match="does not verify"):
        CA.verify_bundle(raw, CLI_SHA, identity=CLI_ID, commit="0" * 40)   # another commit
    with pytest.raises(CA.AttestError, match="does not verify"):
        CA.verify_bundle(_changed(raw), "0" * 64, identity=CLI_ID)          # a statement changed after signing


def _changed(raw: bytes) -> str:
    b = json.loads(raw)
    env = b["dsseEnvelope"]
    st = json.loads(base64.b64decode(env["payload"]))
    st["subject"].append({"name": "x", "digest": {"sha256": "0" * 64}})
    env["payload"] = base64.b64encode(json.dumps(st).encode()).decode()
    return json.dumps(b)


def test_the_fallback_for_a_newer_rekor_log_is_sigstore_python_with_the_same_rules():
    pytest.importorskip("sigstore")
    raw = CA.unsnappy(CLI_BUNDLE.read_bytes()).decode()
    got = CA._verify_with_sigstore_python(raw, CLI_SHA, identity=CLI_ID, commit=CLI_COMMIT, offline=True)
    assert got["ok"] and got["checked_by"] == "sigstore-python" and got["log_index"] == 3010358693 and got["commit"] == CLI_COMMIT
    for kw in ({"identity": CA.IDENTITY, "commit": None}, {"identity": CLI_ID, "commit": "0" * 40}):
        with pytest.raises(CA.AttestError, match="does not verify"):
            CA._verify_with_sigstore_python(raw, CLI_SHA, offline=True, **kw)
    with pytest.raises(CA.AttestError, match="subjects"):
        CA._verify_with_sigstore_python(raw, "0" * 64, identity=CLI_ID, commit=None, offline=True)
    with pytest.raises(CA.AttestError, match="does not verify"):
        CA._verify_with_sigstore_python(_changed(raw.encode()), "0" * 64, identity=CLI_ID, commit=None, offline=True)


def test_bundles_are_read_from_githubs_attestation_api_inline_or_snappy():
    import io
    inline = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    sn = CLI_BUNDLE.read_bytes()
    calls = []

    def opener(req, timeout=0):
        calls.append(req.full_url)
        if "/attestations/sha256:" in req.full_url:
            return io.BytesIO(json.dumps({"attestations": [{"bundle": inline}, {"bundle": None, "bundle_url": "https://blob.example/x.json.sn"}]}).encode())
        return io.BytesIO(sn)
    got = CA.fetch_bundles("a" * 64, opener=opener)
    assert json.loads(got[0]) == inline and got[1] == CA.unsnappy(sn)
    assert calls[0] == "https://api.github.com/repos/drexthealpha/Knos/attestations/sha256:" + "a" * 64


# -- the app server's endpoint, with knos_oidc on chain (LiteSVM) ------------------------------------------------------
def _github_token(aud: str, now: int, **over):
    from _settle import github_claims, sign_jwt, signing_key
    c = github_claims(aud=aud, repository="drexthealpha/Knos", repository_id=ghoidc.REPOSITORY_ID, repository_owner_id=ghoidc.OWNER_ID,
                      repository_owner="drexthealpha", workflow_ref=ghoidc.WORKFLOW_REF, job_workflow_ref=ghoidc.WORKFLOW_REF,
                      sha=RUN_SHA, run_id=ENV["GITHUB_RUN_ID"], run_attempt="1", event_name="schedule", ref="refs/heads/main",
                      sub="repo:drexthealpha/Knos:ref:refs/heads/main", iat=now, nbf=now - 5, exp=now + 300)
    c.update(over)
    return sign_jwt(signing_key(), c)


def _jwks():
    from _settle import b64, modulus, signing_key
    from knos.settle.v2 import oidc
    return {"keys": [{"kty": "RSA", "alg": "RS256", "e": "AQAB", "kid": "k", "n": b64(oidc.modulus_bytes(modulus(signing_key())))}]}


def _coordinator(tmp_path, s):
    c = session.Coordinator({"group_key": s["group_key"], "min": 2}, tmp_path / "sessions")
    c._save({**s, "commitments": {}, "shares": {}, "signers": [], "signing_package": None, "signature": None, "opened": 0, "log": [], "meta": {}})
    return c


def test_the_attest_endpoint_has_knos_oidc_verify_the_runs_token_on_chain_and_records_the_four_proofs(tmp_path):
    pytest.importorskip("solders.litesvm")
    from _oidc2 import Chain2
    from test_relay2 import Net
    from knos.settle.v2 import oidc, relay
    import importlib
    import sys
    sys.path.insert(0, str(ROOT / "apps" / "wanted"))
    referee = importlib.import_module("knos_wanted.referee")

    from _settle import modulus, signing_key
    c2 = Chain2()
    assert c2.register(oidc.GITHUB, modulus(signing_key())), c2.err        # the test build's genesis key (GitHub's own on devnet)
    net, me, now = Net(c2), c2.fund(), c2.now()
    s = _session()
    coord = _coordinator(tmp_path, s)
    raw = _verdict(s)
    sha = hashlib.sha256(raw).hexdigest()
    jwt = _github_token(CA.AUD_PREFIX + sha, now)
    keys, bundles = _jwks(), []
    verify = lambda tok, audience: ghoidc.verify(tok, keys=keys, now=now, audience=audience)              # noqa: E731
    onchain = lambda tok: relay.verify_only(net, me, tok, {oidc.GITHUB: keys}, now=now)                    # noqa: E731

    def bundle_ok(b, sha_, commit):
        bundles.append((b, sha_, commit))
        return {"ok": True, "log_index": 123, "commit": commit, "invocation": "x", "identity": CA.IDENTITY}
    body = {"session": s["id"], "verdict": raw.decode(), "oidc": jwt, "bundle": "{}", "attestation_url": "https://github.com/drexthealpha/Knos/attestations/77"}
    got = referee.attest(body, coord=coord, verify_token=verify, onchain=onchain, check_bundle=bundle_ok)
    assert got["onchain"]["ok"] and got["onchain"]["signatures"] and bundles == [("{}", sha, RUN_SHA)], got["onchain"].get("why")
    assert got["attestation"]["url"].endswith("/attestations/77") and got["attestation"]["rekor"].endswith("logIndex=123")
    # ON CHAIN: the token account is knos_oidc's, VERIFIED, and its claims name the repository, the workflow, the commit and the verdict
    from solders.pubkey import Pubkey
    acct = Pubkey.from_string(got["onchain"]["account"])
    assert c2.svm.get_account(acct).owner == oidc.OIDC_ID
    tok = oidc.read_token(c2.data(acct))
    cl = tok.claims()
    assert tok.verified and tok.issuer == oidc.GITHUB
    assert (cl["repository"], cl["workflow_ref"], cl["sha"], cl["run_id"], cl["aud"]) == ("drexthealpha/Knos", ghoidc.WORKFLOW_REF, RUN_SHA, ENV["GITHUB_RUN_ID"], CA.AUD_PREFIX + sha)
    rec = coord.get(s["id"])["code_referee"]
    assert rec["verdict_sha256"] == sha and rec["run"].endswith("/runs/39128205037/attempts/1") and session.public(coord.get(s["id"]))["code_referee"] == rec
    # posting again changes nothing and sends nothing
    n = net.txs
    assert referee.attest(body, coord=coord, verify_token=verify, onchain=onchain, check_bundle=bundle_ok) == rec and net.txs == n
    # refusals, before anything is sent: a token for another verdict, another commit, another workflow; a verdict of another digest
    s2 = _session(sid="cd" * 16)
    coord._save({**coord.get(s["id"]), **s2, "code_referee": None})
    raw2 = _verdict(s2)
    sha2 = hashlib.sha256(raw2).hexdigest()
    for bad, why in ((_github_token(CA.AUD_PREFIX + sha, now), "aud"), (_github_token(CA.AUD_PREFIX + sha2, now, sha="0" * 40), "another commit"),
                     (_github_token(CA.AUD_PREFIX + sha2, now, workflow_ref="drexthealpha/Knos/.github/workflows/x.yml@refs/heads/main"), "referee.yml")):
        with pytest.raises((PermissionError, CA.AttestError), match=why):
            referee.attest({**body, "session": s2["id"], "verdict": raw2.decode(), "oidc": bad}, coord=coord, verify_token=verify, onchain=onchain, check_bundle=bundle_ok)
    with pytest.raises(CA.AttestError, match="not this session"):
        referee.attest({**body, "session": s2["id"]}, coord=coord, verify_token=verify, onchain=onchain, check_bundle=bundle_ok)
    assert net.txs == n
    # an attestation that does not verify is recorded as such; the on-chain proof still stands
    def bundle_bad(b, sha_, commit):
        raise CA.AttestError("the attestation does not verify: test")
    got2 = referee.attest({**body, "session": s2["id"], "verdict": raw2.decode(), "oidc": _github_token(CA.AUD_PREFIX + sha2, now)},
                          coord=coord, verify_token=verify, onchain=onchain, check_bundle=bundle_bad)
    assert got2["onchain"]["ok"] and got2["attestation"] == {"ok": False, "why": "the attestation does not verify: test"}


def test_the_attest_job_posts_each_verdict_with_a_token_whose_audience_names_it(tmp_path):
    import io
    s = _session()
    raw = _verdict(s)
    (tmp_path / f"verdict-{s['id']}.json").write_bytes(raw)
    (tmp_path / "bundle.jsonl").write_text('{"b": 1}')
    sent = []

    def opener(req, timeout=0):
        sent.append((req.full_url, json.loads(req.data)))
        return io.BytesIO(json.dumps({"onchain": {"ok": True}, "attestation": {"ok": True}}).encode())
    got = CA.post_all(tmp_path, "https://knos.example", bundle_path=str(tmp_path / "bundle.jsonl"), attestation_url="https://github.com/u",
                      token=lambda aud: "TOKEN-for-" + aud, opener=opener)
    url, body = sent[0]
    assert url == "https://knos.example/api/referee/attest" and body["verdict"] == raw.decode() and body["bundle"] == '{"b": 1}'
    assert body["oidc"] == "TOKEN-for-" + CA.audience(raw) and got[0]["onchain"] == {"ok": True}
    with pytest.raises(CA.AttestError):
        CA.post_all(tmp_path, "http://knos.example", token=lambda a: "t", opener=opener)


# -- never asleep: the PC daemon pings too ------------------------------------------------------------------------------
def test_the_pc_daemon_pings_healthz_on_its_own_clock_and_logs_each_ping():
    t = {"now": 1000.0}
    lines, pings = [], []

    class Client:
        def pending(self):
            return []

        def healthz(self):
            pings.append(t["now"])
            return {"status": 200, "ms": 5}
    stop = {"n": 0}

    def sleep(sec):
        t["now"] += sec
        stop["n"] += 1
        if stop["n"] >= 25:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        participant.serve({"id": 3, "group_key": "g"}, Client(), None, every=30, healthz_every=300, clock=lambda: t["now"], sleep=sleep,
                          log=lambda line, **kw: lines.append(json.loads(line)))
    assert pings == [1000.0, 1300.0, 1600.0] and all(x["healthz"]["status"] == 200 and x["id"] == 3 for x in lines)
    # without --healthz-every the daemon never pings
    pings.clear()
    participant.serve({"id": 3}, Client(), None, once=True, log=lambda *a, **k: None)
    assert pings == []



def test_the_pc_daemon_keeps_polling_after_the_network_fails():
    """On 19 Oct 2026 the PC host stopped on one DNS failure (URLError from /api/referee/pending): it must log and poll again."""
    import urllib.error
    calls, lines = [], []

    class Client:
        def pending(self):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.URLError("[Errno -3] Temporary failure in name resolution")
            if len(calls) == 2:
                raise TimeoutError("timed out")
            return []

        def healthz(self):
            return {"status": 200, "ms": 1}

    def sleep(sec):
        if len(calls) >= 3:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        participant.serve({"id": 3, "group_key": "g"}, Client(), None, every=30, sleep=sleep, log=lambda line, **kw: lines.append(json.loads(line)))
    assert len(calls) == 3 and [x["id"] for x in lines] == [3, 3] and "name resolution" in lines[0]["error"] and "timed out" in lines[1]["error"]

def test_healthz_over_http_never_raises():
    import http.server
    import threading
    codes = iter([503, 200])

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(next(codes)); self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = participant.HttpClient(f"http://127.0.0.1:{srv.server_port}")
        assert c.healthz()["status"] == 503 and c.healthz()["status"] == 200
    finally:
        srv.shutdown()
    assert participant.HttpClient("http://127.0.0.1:9", timeout=1).healthz()["status"] is None


# -- the workflow ------------------------------------------------------------------------------------------------------
def test_referee_yml_attests_in_a_job_that_holds_no_share_and_posts_with_its_own_token():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((WF / "referee.yml").read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    assert doc["permissions"] == {} and sorted(jobs) == ["attest", "sign"]
    assert jobs["sign"]["permissions"] == {"contents": "read", "id-token": "write"}
    assert jobs["attest"]["permissions"] == {"contents": "read", "id-token": "write", "attestations": "write"}
    text = json.dumps(jobs["attest"])
    assert "secrets." not in text and "KNOS_REFEREE_FROST_SHARE" not in text and "secrets.KNOS_REFEREE_FROST_SHARE" in json.dumps(jobs["sign"])
    assert jobs["attest"]["needs"] == "sign" and "needs.sign.outputs.verdicts" in jobs["attest"]["if"]
    uses = [s.get("uses", "").split("@")[0] for s in jobs["attest"]["steps"]]
    assert uses == ["actions/checkout", "actions/download-artifact", "actions/attest-build-provenance", ""]
    att = jobs["attest"]["steps"][2]
    assert att["with"] == {"subject-path": "referee-verdicts/verdict-*.json"}
    assert jobs["attest"]["steps"][-1]["run"].startswith("python3 -m knos.threshold.codeattest post --dir referee-verdicts")
    sign = json.dumps(jobs["sign"]["steps"])
    assert "--verdicts referee-verdicts" in sign and "actions/upload-artifact" in sign and "attest-build-provenance" not in sign
