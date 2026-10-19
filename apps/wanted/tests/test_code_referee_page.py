"""The project milestone page shows the code referee's four proofs for each order (knos_wanted.referee.trust): the
GitHub Actions run, the knos_oidc verification transaction, the Sigstore attestation and the FROST release. The
proofs themselves are tested in tests/test_threshold_codeattest.py (on chain in LiteSVM, the bundle against Sigstore's
trust root); here: what the page is given and what it draws."""
from __future__ import annotations

from pathlib import Path

from knos.threshold import session as S
from knos_wanted import referee, valley

STATIC = Path(__file__).resolve().parents[1] / "knos_wanted" / "static"


def _coord(tmp_path, monkeypatch, **extra):
    c = S.Coordinator({"group_key": "G", "min": 2}, tmp_path / "s")
    s = {"id": "ab" * 16, "state": "signed", "digest": "11" * 32, "request": {}, "group_key": "G", "min": 2, "signers": [1, 2],
         "signing_package": None, "signature": "aa" * 64, "commitments": {}, "shares": {}, "opened": 0, "log": [], "meta": {}, **extra}
    c._save(s)
    monkeypatch.setattr(referee, "enabled", lambda: True)
    monkeypatch.setattr(referee, "coordinator", lambda: c)
    return s


def test_an_order_with_a_referee_session_carries_the_four_proofs(tmp_path, monkeypatch):
    s = _coord(tmp_path, monkeypatch, result={"status": "released", "signatures": ["RELEASE_SIG"]},
               code_referee={"run": "https://github.com/drexthealpha/Knos/actions/runs/1/attempts/1", "commit": "e" * 40, "verdict_sha256": "f" * 64,
                             "onchain": {"ok": True, "signatures": ["WRITE_SIG", "STEP_SIG"], "account": "TokAcct"},
                             "attestation": {"ok": True, "log_index": 7, "rekor": "https://search.sigstore.dev/?logIndex=7",
                                             "url": "https://github.com/drexthealpha/Knos/attestations/9"}})
    o = {"order": "11111111111111111111111111111111", "status": "released", "signatures": {"referee_group_pass": "RELEASE_SIG"},
         "referee_session": {"id": s["id"]}}
    t = valley._order_public(o)["trust"]
    assert t["run"].endswith("/runs/1/attempts/1") and t["oidc_verify"] == ["STEP_SIG"] and t["oidc_account"] == "TokAcct"
    assert t["attestation"]["ok"] and t["release"] == "RELEASE_SIG" and t["frost_signature"] == "aa" * 64 and t["signers"] == [1, 2]
    # an order with no session, or a server that is not a FROST host, shows nothing (and the page never fails on it)
    assert valley._order_public({**o, "referee_session": None})["trust"] is None
    monkeypatch.setattr(referee, "enabled", lambda: False)
    assert valley._order_public(o)["trust"] is None


def test_a_session_still_signing_says_what_is_missing(tmp_path, monkeypatch):
    s = _coord(tmp_path, monkeypatch, state="round2", signature=None)
    t = referee.trust(s["id"])
    assert (t["run"], t["oidc_verify"], t["attestation"], t["release"], t["state"]) == (None, None, None, None, "round2")


def test_the_page_draws_one_link_per_proof_and_the_group_release():
    js = (STATIC / "valley.js").read_text(encoding="utf-8")
    body = js[js.index("function trustLine"):js.index("function msCard")]
    for label in ("referee run", "knos_oidc verification", "Sigstore attestation", "Rekor", "FROST release"):
        assert label in body, label
    assert "${trustLine(o.trust)}" in js and "o.signatures.referee_group_pass" in js       # the FROST release link too
