"""knos-oidc 0.3.35 (programs-v2/knos_oidc, pins.rs ROTATE_REF_KNOS): the pinned rotate workflow is accepted in BOTH of
its homes, drexthealpha/knos-oidc-rotate and Knos's branch `oidc-rotate` (the same commits, so the same ROTATE_SHA and
ROTATE_SHA2), and nowhere else: not someone else's Knos, not a repository whose name only starts like Knos, not another
case. LiteSVM, the testkeys build tests/fixtures/knos_oidc_v2_0335_test.so (scripts/build_programs_v2.sh oidc). The
committed 0.3.34 test build refuses the new home, which is why the founder's upgrade is needed
(docs/reference/CUTOVER-0331.md section 2, deploy/upgrade-0335/STEPS.md)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("solders.litesvm")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from _oidc2 import GH, TEST_ROTATE_SHA, Chain2  # noqa: E402
from _settle import modulus, signing_key  # noqa: E402

from knos.settle.v2 import oidc  # noqa: E402
from knos.settle.v2 import relay  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUILD = "knos_oidc_v2_0335_test.so"
OLD = "drexthealpha/knos-oidc-rotate/.github/workflows/rotate.yml@refs/heads/main"
KNOS = "drexthealpha/Knos/.github/workflows/rotate.yml@refs/heads/oidc-rotate"
SHAS = (TEST_ROTATE_SHA, oidc.IDS["rotate_sha"], oidc.IDS["rotate_sha2"])
LOOK_ALIKES = {
    "someone else's Knos": "someone/Knos/.github/workflows/rotate.yml@refs/heads/main",
    "a repository whose name starts like Knos": "drexthealpha/Knos-x/.github/workflows/rotate.yml@refs/heads/main",
    "a repository whose name only starts with Knos": "drexthealpha/Knosx/.github/workflows/rotate.yml@refs/heads/main",
    "Knos in lower case": "drexthealpha/knos/.github/workflows/rotate.yml@refs/heads/main",
    "Knos in capitals": "drexthealpha/KNOS/.github/workflows/rotate.yml@refs/heads/main",
    "the owner in capitals": "DREXTHEALPHA/Knos/.github/workflows/rotate.yml@refs/heads/main",
    "an owner that ends like drexthealpha": "xdrexthealpha/Knos/.github/workflows/rotate.yml@refs/heads/main",
    "another file in Knos": "drexthealpha/Knos/.github/workflows/claim.yml@refs/heads/main",
    "rotate.yaml in Knos": "drexthealpha/Knos/.github/workflows/rotate.yaml@refs/heads/main",
    "the file in a folder of Knos": "drexthealpha/Knos/workflows/knos-oidc-rotate/.github/workflows/rotate.yml@refs/heads/main",
}
MINE = dict(event_name="workflow_dispatch", repository_owner_id="555000", actor_id="555000", repository_id="777000111",
            repository="someone/rotate-knos", repository_owner="someone", actor="someone")


def code(c: Chain2) -> int | None:
    m = re.search(r"Custom\((\d+)\)", c.err or "")
    return int(m.group(1)) if m else None


def new_key() -> int:
    return modulus(rsa.generate_private_key(public_exponent=65537, key_size=2048))


@pytest.fixture(scope="module")
def chain():
    c = Chain2(BUILD)
    assert c.register(GH, modulus(signing_key())), c.err
    return c


def test_the_rotate_workflow_registers_a_key_from_either_home_at_each_pinned_commit(chain):
    c = chain
    for ref in (OLD, KNOS):
        for sha in SHAS:
            n = new_key()
            tok = c.attest(GH, n, job_workflow_ref=ref, job_workflow_sha=sha)
            assert tok is not None, c.err
            assert c.register(GH, n, tok), f"{ref} @ {sha}: {c.err}"
            k = c.key(GH, n)
            assert k is not None and not k.genesis and not k.approved


def test_a_key_registered_from_the_old_home_is_refreshed_from_the_new_one_and_back(chain):
    c = chain
    n = new_key()
    assert c.register(GH, n, c.attest(GH, n, job_workflow_ref=OLD)), c.err
    for ref in (KNOS, OLD, KNOS):
        c.warp(2 * 86_400)
        assert c.refresh(GH, n, c.attest(GH, n, job_workflow_ref=ref)), f"{ref}: {c.err}"
        assert c.key(GH, n).expires_at == c.now() + oidc.KEY_TTL


def test_anyone_keeps_a_key_alive_with_the_workflow_from_its_knos_home(chain):
    c = chain
    n = new_key()
    assert c.register(GH, n, c.attest(GH, n)), c.err
    c.warp(2 * 86_400)
    stranger = c.fund()
    assert c.refresh(GH, n, c.attest(GH, n, job_workflow_ref=KNOS, **MINE), payer=stranger), c.err
    assert c.key(GH, n).expires_at == c.now() + oidc.KEY_TTL
    # and that run still registers nothing
    other = new_key()
    tok = c.attest(GH, other, job_workflow_ref=KNOS, **MINE)
    assert tok is not None and not c.send([c.register_ix(GH, other, tok)]) and code(c) == 74


def test_look_alikes_of_the_new_home_are_refused_for_register_and_refresh(chain):
    c = chain
    have = new_key()
    assert c.register(GH, have, c.attest(GH, have)), c.err
    expires = c.key(GH, have).expires_at
    c.warp(3_600)
    wrong = {**LOOK_ALIKES, "the Knos home at another commit": KNOS}
    for what, ref in wrong.items():
        sha = "2" * 40 if what == "the Knos home at another commit" else TEST_ROTATE_SHA
        n = new_key()
        tok = c.attest(GH, n, job_workflow_ref=ref, job_workflow_sha=sha)
        assert tok is not None, c.err
        assert not c.send([c.register_ix(GH, n, tok)]) and code(c) == 74, f"register, {what}: {c.err}"
        assert c.key(GH, n) is None
        for over in ({}, MINE):                          # the attester's run, and anyone's run by hand
            tok = c.attest(GH, have, job_workflow_ref=ref, job_workflow_sha=sha, **over)
            assert tok is not None, c.err
            assert not c.send([c.refresh_ix(GH, have, tok)]) and code(c) == 74, f"refresh, {what}: {c.err}"
    assert c.key(GH, have).expires_at == expires


def test_the_build_before_this_change_refuses_the_new_home():
    """tests/fixtures/knos_oidc_v2_test.so (what runs before the upgrade) takes only the old home: until the founder's
    upgrade executes, a rotate caller in Knos would attest nothing, so the callers move only after it."""
    c = Chain2()
    assert c.register(GH, modulus(signing_key())), c.err
    n = new_key()
    tok = c.attest(GH, n, job_workflow_ref=KNOS)
    assert tok is not None and not c.send([c.register_ix(GH, n, tok)]) and code(c) == 74
    assert c.register(GH, n, c.attest(GH, n, job_workflow_ref=OLD)), c.err


def test_the_source_and_the_relay_name_the_same_two_prefixes():
    pins = (ROOT / "programs-v2" / "knos_oidc" / "src" / "pins.rs").read_text(encoding="utf-8")
    assert f'pub const ROTATE_REF: &[u8] = b"{relay.ROTATE_REF}";' in pins
    assert f'pub const ROTATE_REF_KNOS: &[u8] = b"{relay.ROTATE_REF_KNOS}";' in pins
    assert relay.ROTATE_REFS == (relay.ROTATE_REF, relay.ROTATE_REF_KNOS)
    lib = (ROOT / "programs-v2" / "knos_oidc" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "pins::rotate_ref(&wref)" in lib and "starts_with(pins::ROTATE_REF)" not in lib
    # the first deployment has no upgrade authority: its pin stays the old home only
    first = (ROOT / "programs" / "knos_oidc" / "src" / "pins.rs").read_text(encoding="utf-8")
    assert "ROTATE_REF_KNOS" not in first
