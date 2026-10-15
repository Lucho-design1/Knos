"""knos.platform.verdict: the off-chain mirror of knos_pay's m-of-n referee verdict (synthetic keys and data)."""
from __future__ import annotations

import pytest
from solders.keypair import Keypair

from knos.platform import verdict as v

JOB, EVIDENCE, RECIPIENT = bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32
NOW = 1_790_000_000


def msg(verdict="PASS", amount=5_000_000, recipient=RECIPIENT, expiry=NOW + 3600, nonce=7) -> bytes:
    return v.message(JOB, EVIDENCE, verdict, amount, recipient, expiry, nonce)


def test_a_message_is_its_seven_fields_and_nothing_else():
    m = msg()
    assert len(m) == v.LENGTH and v.parse(m) == {"job": JOB, "evidence_hash": EVIDENCE, "verdict": "PASS", "amount": 5_000_000,
                                                 "recipient": RECIPIENT, "expiry": NOW + 3600, "nonce": 7}
    assert v.outcome(m) == "release" and v.outcome(msg("FAIL")) == "refund"
    for bad in [dict(verdict="pass"), dict(verdict="MAYBE"), dict(recipient=bytes(31)), dict(amount=-1), dict(amount=2 ** 64), dict(nonce="7")]:
        with pytest.raises(ValueError):
            msg(**bad)
    with pytest.raises(ValueError):
        v.message(bytes(33), EVIDENCE, "PASS", 1, RECIPIENT, NOW, 1)
    for bad in [b"", m[:-1], m + b"x", b"x" + m[1:]]:
        with pytest.raises(ValueError):
            v.parse(bad)


def test_m_distinct_registered_signatures_before_expiry_and_once_per_job_and_nonce():
    panel = [Keypair() for _ in range(3)]
    keys = [bytes(k.pubkey()) for k in panel]
    m = msg()
    s = [v.sign(m, k) for k in panel]
    assert v.check(m, s[:2], keys, 2, now=NOW, used=set())[0]
    assert v.check(m, s, keys, 3, now=NOW, used=set())[0]
    # below threshold; a repeated key; an outsider; a bad signature
    assert v.check(m, s[:1], keys, 2, now=NOW, used=set()) == (False, "below threshold: 1 of 2")
    assert not v.check(m, [s[0], s[0]], keys, 2, now=NOW, used=set())[0]
    outsider = Keypair()
    assert not v.check(m, [s[0], v.sign(m, outsider)], keys, 2, now=NOW, used=set())[0]
    assert not v.check(m, [s[0], (s[1][0], bytes(64))], keys, 2, now=NOW, used=set())[0]
    # expiry and replay
    assert v.check(m, s[:2], keys, 2, now=NOW + 3600, used=set()) == (False, "expired")
    assert not v.check(m, s[:2], keys, 2, now=NOW, used={(JOB, 7)})[0]
    assert v.check(m, s[:2], keys, 2, now=NOW, used={(JOB, 8)})[0]
    # another amount or recipient than the one signed
    for other in [msg(amount=5_000_001), msg(recipient=bytes([4]) * 32)]:
        assert not v.check(other, s, keys, 2, now=NOW, used=set())[0]
