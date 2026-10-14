"""One-transaction verification (knos.platform.verify, programs-v2/knos_oidc/src/rsa64.rs + modexp.rs).

The test build of knos-oidc for sBPF v2 (tests/fixtures/platform/knos_oidc_v2_test.so, scripts/build_sbf.sh v2 test)
does its RSA on 64-bit limbs: ONE Step(16) verifies a 2048-bit GitHub token, of any size up to MAX_JWT, inside one
transaction's 1,400,000 compute units. The v0 build (the fixture every other test loads, what devnet runs today)
cannot: the same Step(16) runs out. The two-step plan works under both, and a token stepped halfway under one build
finishes under the other (the running power is the same bytes). A v1 transaction carries the whole token and the
Step at once. The compute units are printed (pytest -s) and docs/reference/PLATFORM.md records them.

Note: LiteSVM as solders 0.29.0 ships does not load an sBPF v3 ELF ("invalid file header"); the v3 build's numbers
come from solana-test-validator 4.4.0-beta.0 (scripts in docs/reference/PLATFORM.md).
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("solders.litesvm")

from solders.transaction import VersionedTransaction  # noqa: E402

from _oidc2 import GH, GL, Chain2  # noqa: E402
from _settle import FIX, github_claims, gitlab_claims, modulus, sign_jwt, signing_key, sized_jwt  # noqa: E402

from knos import chain as kchain  # noqa: E402
from knos.platform import verify  # noqa: E402
from knos.settle.v2 import oidc  # noqa: E402

FAST = FIX / "platform" / "knos_oidc_v2_test.so"
SLOW = "knos_oidc_v2_test.so"          # the v0 build the other tests load
MARGIN = 1_400_000 - 100_000           # one verification leaves at least 100,000 units for what rides with it


def _chain(build) -> Chain2:
    c = Chain2(oidc_build=str(build))
    assert c.register(GH, modulus(signing_key(2048))), c.err
    assert c.register(GL, modulus(signing_key(4096))), c.err
    return c


def _jwt(size: int = 0, bits: int = 2048) -> str:
    claims = (github_claims if bits == 2048 else gitlab_claims)(aud="knos2:pay:987654321:7:1234567:" + "a" * 40 + ":" + "c" * 64 + ":0:-",
                                                                groups_direct=["g"])
    return sign_jwt(signing_key(bits), claims) if not size else sized_jwt(signing_key(bits), claims, size)


def test_the_builds_say_their_sbpf_version_and_the_plan_follows_the_setting(monkeypatch):
    assert verify.sbpf_version((FIX / SLOW).read_bytes()) == 0 and verify.sbpf_version(FAST.read_bytes()) == 2
    assert verify.sbpf_version(b"not an elf") is None and not verify.fast(None)
    monkeypatch.delenv("KNOS_OIDC_VERIFY", raising=False)
    assert verify.plan(2048) == oidc.step_plan(2048) == [8, 8] and verify.plan(4096) == [2, 3, 3, 3, 4, 1]
    assert verify.plan(2048, "one") == [16] and verify.plan(2048, "auto", FAST.read_bytes()) == [16]
    assert verify.plan(2048, "auto", (FIX / SLOW).read_bytes()) == [8, 8] and verify.plan(2048, "auto") == [8, 8]
    # the sBPF v3 of Agave 4.4 has no 128-bit multiply: a v3 build keeps 32-bit limbs and the two-step plan
    v3 = bytearray(FAST.read_bytes()[:64]); v3[48:52] = (3).to_bytes(4, "little")
    assert verify.sbpf_version(bytes(v3)) == 3 and verify.plan(2048, "auto", bytes(v3)) == [8, 8]
    monkeypatch.setenv("KNOS_OIDC_VERIFY", "one")
    assert oidc.step_plan(2048) == [16] and sum(oidc.step_plan(4096)) == 16
    with pytest.raises(ValueError):
        verify.plan(2048, "three")
    with pytest.raises(ValueError):
        verify.plan(3072)


@pytest.mark.parametrize("size", [0, 3_500, oidc.MAX_JWT])
def test_one_step_verifies_a_2048_bit_token_in_one_transaction_under_the_v2_build(size):
    c = _chain(FAST)
    jwt = _jwt(size)
    tok = c.verify(jwt, GH, modulus(signing_key()), tag="one", plan=[16])
    assert tok is not None, c.err
    t = oidc.read_token(c.data(tok))
    assert t.verified and t.issuer == GH and t.claims() == json.loads(oidc._unb64(jwt.split(".")[1]))
    cu = c.cu["one_2048_step1"][-1]
    print(f"\nCU one Step(16), sBPF v2 build, 2048-bit, {len(jwt)}-byte token: {cu}")
    assert cu < MARGIN


def test_the_v0_build_cannot_and_the_two_step_path_still_works_under_both():
    slow = _chain(SLOW)
    assert slow.verify(_jwt(), GH, modulus(signing_key()), plan=[16]) is None
    assert "ComputationalBudgetExceeded" in slow.err or "ProgramFailedToComplete" in slow.err, slow.err
    for build in (SLOW, FAST):
        c = _chain(build)
        assert c.verify(_jwt(), GH, modulus(signing_key()), tag="two", plan=[8, 8]) is not None, c.err
        print(f"\nCU Step(8), Step(8) under the sBPF v{verify.sbpf_version((FIX / build).read_bytes())} build:{[c.cu[f'two_2048_step{i}'][-1] for i in (1, 2)]}")
    # a forged signature is refused by the one-step path as by the other (70: bad signature)
    c = _chain(FAST)
    head, body, sig = _jwt().split(".")
    bad = f"{head}.{body}.{sig[:40]}{'A' if sig[40] != 'A' else 'B'}{sig[41:]}"
    assert c.verify(bad, GH, modulus(signing_key()), plan=[16]) is None
    assert "Custom(70)" in c.err or "Custom(65)" in c.err, c.err


def test_a_token_stepped_halfway_under_one_build_finishes_under_the_other():
    """An upgrade between two Steps changes nothing: the running power in the token account is the same bytes."""
    for first, then in ((SLOW, FAST), (FAST, SLOW)):
        c = _chain(first)
        jwt, p = _jwt(), c.payer
        tid = oidc.token_id(jwt)
        c.write(jwt, p)
        key = oidc.key_pda(GH, modulus(signing_key()))
        assert c.send([oidc.step_ix(p.pubkey(), tid, key, 8)], p), c.err
        c.svm.add_program_from_file(oidc.OIDC_ID, str(FIX / then) if isinstance(then, str) else str(then))
        assert c.send([oidc.step_ix(p.pubkey(), tid, key, 8)], p), c.err
        assert oidc.read_token(c.data(oidc.token_pda(p.pubkey(), tid))).verified


def test_4096_bit_keys_under_the_v2_build():
    c = _chain(FAST)
    for size in (0, oidc.MAX_JWT):
        jwt = _jwt(size, 4096)
        plan = verify.ONE_STEP[4096]
        assert c.verify(jwt, GL, modulus(signing_key(4096)), tag=f"g{size}", plan=plan) is not None, c.err
        cu = [c.cu[f"g{size}_4096_step{i + 1}"][-1] for i in range(len(plan))]
        print(f"\nCU 4096-bit, {len(jwt)}-byte token, sBPF v2 build, plan {plan}: {cu}")
        assert max(cu) < MARGIN


def test_a_v1_transaction_writes_and_verifies_the_token_at_once(monkeypatch):
    monkeypatch.setattr(kchain, "V1_BUDGET_IX", True)      # LiteSVM reads the limit from the instruction (knos.chain)
    c = _chain(FAST)
    p = c.payer
    jwt = _jwt()
    ixs = verify.one_transaction_ixs(p.pubkey(), jwt, oidc.key_pda(GH, modulus(signing_key())))
    size = kchain.tx_size(ixs, p.pubkey(), v1=True)
    assert kchain.MAX_TX_BYTES < size <= kchain.MAX_V1_BYTES and verify.fits_v1(ixs, p.pubkey())
    assert kchain.tx_size(ixs, p.pubkey()) > kchain.MAX_TX_BYTES          # no legacy transaction holds it
    tx = kchain.sign(ixs, p, [], c.svm.latest_blockhash(), v1=True)
    assert c._sent(c.svm.send_transaction(tx), "v1"), c.err
    assert oidc.read_token(c.data(oidc.token_pda(p.pubkey(), oidc.token_id(jwt)))).verified
    print(f"\nCU one v1 transaction ({size} bytes): Write + Step(16): {c.cu['v1'][-1]}")
    assert isinstance(tx, VersionedTransaction)
