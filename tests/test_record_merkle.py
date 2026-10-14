"""Knos Record's Merkle tree (RFC 9162 section 2.1): known answers, and an audit path for every line of every size."""

from __future__ import annotations

import hashlib

import pytest

from knos.record import merkle


def h(i: int) -> str:
    return hashlib.sha256(str(i).encode()).hexdigest()


def test_known_answers():
    assert merkle.root([]) == hashlib.sha256(b"").hexdigest()
    one = hashlib.sha256(b"\x00" + bytes.fromhex(h(0))).digest()
    assert merkle.root([h(0)]) == one.hex()
    two = hashlib.sha256(b"\x00" + bytes.fromhex(h(1))).digest()
    assert merkle.root([h(0), h(1)]) == hashlib.sha256(b"\x01" + one + two).hexdigest()
    three = hashlib.sha256(b"\x00" + bytes.fromhex(h(2))).digest()       # 3 leaves split 2 | 1, not duplicated
    assert merkle.root([h(0), h(1), h(2)]) == hashlib.sha256(b"\x01" + hashlib.sha256(b"\x01" + one + two).digest() + three).hexdigest()


def test_any_change_order_or_count_changes_the_root():
    base = [h(i) for i in range(7)]
    r = merkle.root(base)
    assert merkle.root(base[:-1]) != r and merkle.root(base + [h(7)]) != r
    assert merkle.root([base[1], base[0], *base[2:]]) != r
    assert merkle.root([*base[:3], h(99), *base[4:]]) != r


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 9, 16, 17])
def test_every_line_has_an_audit_path_and_a_wrong_one_fails(n):
    leaves = [h(i) for i in range(n)]
    r = merkle.root(leaves)
    for i in range(n):
        path = merkle.proof(leaves, i)
        assert merkle.check_proof(leaves[i], i, n, path, r)
        assert not merkle.check_proof(h(1000), i, n, path, r)
        if n > 1:
            assert not merkle.check_proof(leaves[i], (i + 1) % n, n, path, r)
    with pytest.raises(IndexError):
        merkle.proof(leaves, n)
