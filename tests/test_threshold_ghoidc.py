"""Referee host 2 (GitHub Actions) authenticates with its GitHub Actions OIDC token, not a founder-made token
(knos.threshold.ghoidc, .github/workflows/referee.yml). The tokens here are signed by a locally generated TEST RSA
key published in a local JWKS (GitHub signs the real ones); nothing is fetched from the network."""
from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("cryptography")

from solders.keypair import Keypair  # noqa: E402

from knos import threshold as T  # noqa: E402
from knos.threshold import ghoidc, participant, session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "referee.yml"


def _rsa(kid="gh-test-1"):
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = k.public_key().public_numbers()
    b = lambda i: base64.urlsafe_b64encode(i.to_bytes((i.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()  # noqa: E731
    return k, {"keys": [{"kty": "RSA", "kid": kid, "n": b(n.n), "e": b(n.e), "alg": "RS256", "use": "sig"}]}


def _jwt(k, claims, kid="gh-test-1", alg="RS256"):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    e = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()  # noqa: E731
    si = f"{e({'alg': alg, 'kid': kid, 'typ': 'JWT'})}.{e(claims)}"
    return si + "." + base64.urlsafe_b64encode(k.sign(si.encode(), padding.PKCS1v15(), hashes.SHA256())).rstrip(b"=").decode()


def _claims(now=None, **over):
    now = int(time.time()) if now is None else now
    c = {"iss": ghoidc.ISSUER, "aud": "knos-referee", "iat": now, "nbf": now, "exp": now + 300,
         "sub": "repo:drexthealpha/Knos:ref:refs/heads/main", "repository": "drexthealpha/Knos", "repository_id": "1353152983",
         "repository_owner": "drexthealpha", "repository_owner_id": "142920951", "ref": "refs/heads/main", "event_name": "schedule",
         "workflow_ref": "drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main",
         "job_workflow_ref": "drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main", "run_id": "1", "jti": "j"}
    c.update(over)
    return {k: v for k, v in c.items() if v is not None}


def test_a_github_actions_token_of_referee_yml_on_main_is_accepted_and_keys_come_from_githubs_discovery_document():
    k, jwks = _rsa()
    seen = []

    def fetch(url):
        seen.append(url)
        return {"issuer": ghoidc.ISSUER, "jwks_uri": ghoidc.ISSUER + "/.well-known/jwks"} if url == ghoidc.DISCOVERY else jwks
    ghoidc._keys.update(at=0.0, set=None)
    got = ghoidc.verify(_jwt(k, _claims()), fetch=fetch)
    assert got["repository"] == "drexthealpha/Knos" and seen == [ghoidc.DISCOVERY, ghoidc.ISSUER + "/.well-known/jwks"]
    assert ghoidc.verify(_jwt(k, _claims(event_name="workflow_dispatch")), fetch=fetch)       # cached keys: no new fetch
    assert len(seen) == 2
    with pytest.raises(ghoidc.GithubOidcError, match="another issuer"):
        ghoidc.jwks(lambda u: {"issuer": "https://example.org", "jwks_uri": "x"})
    ghoidc._keys.update(at=0.0, set=None)


@pytest.mark.parametrize("why,over", [
    ("aud", {"aud": "sts.amazonaws.com"}), ("iss", {"iss": "https://example.org"}),
    ("repository", {"repository": "someone/Knos"}), ("repository_id", {"repository_id": "1"}),
    ("owner_id", {"repository_owner_id": "2"}),
    ("workflow", {"workflow_ref": "drexthealpha/Knos/.github/workflows/other.yml@refs/heads/main"}),
    ("branch workflow", {"workflow_ref": "drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/dev"}),
    ("reusable caller", {"job_workflow_ref": "evil/x/.github/workflows/referee.yml@refs/heads/main"}),
    ("ref", {"ref": "refs/pull/1/merge"}), ("event", {"event_name": "pull_request_target"}),
    ("expired", {"exp": int(time.time()) - 3600, "nbf": int(time.time()) - 4000, "iat": int(time.time()) - 4000}),
    ("not yet", {"nbf": int(time.time()) + 3600, "iat": int(time.time()) + 3600, "exp": int(time.time()) + 4000}),
])
def test_any_other_token_is_refused(why, over):
    k, jwks = _rsa()
    with pytest.raises(ghoidc.GithubOidcError):
        ghoidc.verify(_jwt(k, _claims(**over)), keys=jwks)


def test_a_token_signed_by_another_key_tampered_or_not_rs256_is_refused():
    k, jwks = _rsa()
    k2, _ = _rsa()
    with pytest.raises(ghoidc.GithubOidcError, match="signature"):
        ghoidc.verify(_jwt(k2, _claims()), keys=jwks)
    with pytest.raises(ghoidc.GithubOidcError, match="signature"):
        ghoidc.verify(_jwt(k, _claims(), kid="unknown"), keys=jwks)
    h, p, s = _jwt(k, _claims()).split(".")
    forged = base64.urlsafe_b64encode(json.dumps(_claims(repository="evil/Knos")).encode()).rstrip(b"=").decode()
    with pytest.raises(ghoidc.GithubOidcError, match="signature"):
        ghoidc.verify(f"{h}.{forged}.{s}", keys=jwks)
    with pytest.raises(ghoidc.GithubOidcError, match="RS256"):
        ghoidc.verify(_jwt(k, _claims(), alg="none"), keys=jwks)
    with pytest.raises(ghoidc.GithubOidcError, match="JWT"):
        ghoidc.verify("not-a-token", keys=jwks)


def _group_and_shares():
    kps = {i: Keypair() for i in (1, 2, 3)}
    group = {"kind": T.GROUP_KIND, "group_key": "test", "min": 2, "max": 3,
             "hosts": {str(i): {"name": T.HOSTS[i], "transport_key": str(kp.pubkey())} for i, kp in kps.items()}}
    shares = {i: {"kind": T.SHARE_KIND, "id": i, "group_key": "test", "transport_secret": str(kp)} for i, kp in kps.items()}
    return group, shares


def test_the_coordinator_takes_host_2s_posts_only_with_a_valid_github_oidc_token(tmp_path):
    k, jwks = _rsa()
    group, shares = _group_and_shares()
    coord = session.Coordinator(group, tmp_path / "s", host_auth={ghoidc.GH_HOST: lambda t: ghoidc.verify(t, keys=jwks)})
    sid = coord.open({"kind": "test"}, bytes(32))["id"]
    body = {"hiding": "00", "binding": "00"}                       # one commitment: no FROST call happens below two
    sig = T.auth(shares[2], "commit", sid, body)
    with pytest.raises(PermissionError, match="identity token"):
        coord.commit(sid, 2, body, sig)                               # transport signature alone: refused
    with pytest.raises(PermissionError, match="workflow"):
        coord.commit(sid, 2, body, sig, _jwt(k, _claims(workflow_ref="drexthealpha/Knos/.github/workflows/x.yml@refs/heads/main")))
    k2, _ = _rsa()
    with pytest.raises(PermissionError, match="signature"):
        coord.commit(sid, 2, body, sig, _jwt(k2, _claims()))
    with pytest.raises(PermissionError, match="transport"):
        coord.commit(sid, 2, body, T.auth(shares[3], "commit", sid, body), _jwt(k, _claims()))   # a good token, 3's key
    assert coord.get(sid)["commitments"] == {}
    coord.commit(sid, 2, body, sig, _jwt(k, _claims()))
    assert coord.get(sid)["commitments"] == {"2": body} and coord.get(sid)["state"] == session.ROUND1
    # hosts 1 and 3 (the app server in-process, the PC daemon) are not asked for a GitHub token
    sid3 = coord.open({"kind": "test"}, bytes(32))["id"]
    coord.commit(sid3, 3, body, T.auth(shares[3], "commit", sid3, body))
    assert coord.get(sid3)["commitments"] == {"3": body}


def test_the_github_host_adds_a_fresh_runner_token_to_every_post():
    calls = []
    c = participant.HttpClient("http://127.0.0.1:9", host_token=lambda: calls.append(1) or f"tok{len(calls)}")
    assert c._proof({"a": 1}) == {"a": 1, "oidc": "tok1"} and c._proof({})["oidc"] == "tok2"
    assert participant.HttpClient("http://127.0.0.1:9")._proof({"a": 1}) == {"a": 1}

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    got = {}

    def opener(req, timeout):
        got["url"], got["auth"] = req.full_url, req.get_header("Authorization")
        return R(json.dumps({"value": "the.id.token"}).encode())
    env = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://runner.example/token?api-version=2.0", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "rt"}
    assert ghoidc.request_token(env=env, opener=opener) == "the.id.token"
    assert got == {"url": "https://runner.example/token?api-version=2.0&audience=knos-referee", "auth": "Bearer rt"}
    with pytest.raises(ghoidc.GithubOidcError, match="id-token: write"):
        ghoidc.request_token(env={})


def test_referee_yml_polls_on_a_cron_and_needs_no_founder_token():
    doc = yaml.safe_load(WF.read_text(encoding="utf-8"))
    on = doc[True] if True in doc else doc["on"]
    assert on["schedule"] == [{"cron": "*/5 * * * *"}] and "workflow_dispatch" in on
    # 0.3.29 G-TRUST: the workflow grants nothing; the signing job gets what it had (the attest job: tests/test_threshold_codeattest.py)
    assert doc["permissions"] == {} and doc["jobs"]["sign"]["permissions"] == {"contents": "read", "id-token": "write"}
    text = WF.read_text(encoding="utf-8")
    import re
    assert re.findall(r"secrets\.(\w+)", text) == ["KNOS_REFEREE_FROST_SHARE"]
    assert "/api/referee/pending" in text and text.count("--github-oidc") == 2
    for f in (ROOT / "render.yaml", ROOT / "apps" / "wanted" / "knos_wanted" / "referee.py", WF):
        assert "KNOS_REFEREE_GH_TOKEN" not in f.read_text(encoding="utf-8"), f
    assert ghoidc.WORKFLOW_REF == "drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main" and ghoidc.AUDIENCE == "knos-referee"
