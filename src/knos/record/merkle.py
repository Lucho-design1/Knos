"""A Merkle tree over a batch of record lines, as Certificate Transparency builds one (RFC 9162 section 2.1): a leaf
is sha256(0x00 || line hash), a node sha256(0x01 || left || right), and a batch of n lines splits at the largest power
of two below n. One root stands for every line of the batch in order; changing, adding, removing or reordering any line
changes it. `proof` and `check_proof` show one line is in an anchored batch without the rest of the journal.
"""

from __future__ import annotations

import hashlib

EMPTY = hashlib.sha256(b"").hexdigest()


def leaf(line_hash: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(line_hash)).digest()


def node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _root(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return leaves[0]
    k = _split(len(leaves))
    return node(_root(leaves[:k]), _root(leaves[k:]))


def root(line_hashes: list[str]) -> str:
    """The batch's root in hex; sha256 of nothing for an empty batch."""
    if not line_hashes:
        return EMPTY
    return _root([leaf(h) for h in line_hashes]).hex()


def _path(leaves: list[bytes], m: int) -> list[bytes]:
    if len(leaves) <= 1:
        return []
    k = _split(len(leaves))
    if m < k:
        return _path(leaves[:k], m) + [_root(leaves[k:])]
    return _path(leaves[k:], m - k) + [_root(leaves[:k])]


def proof(line_hashes: list[str], index: int) -> list[str]:
    """The audit path of line `index` of the batch (RFC 9162 2.1.3.1), leaf side first."""
    if not 0 <= index < len(line_hashes):
        raise IndexError(f"the batch has {len(line_hashes)} lines; there is no line {index}")
    return [h.hex() for h in _path([leaf(h) for h in line_hashes], index)]


def check_proof(line_hash: str, index: int, size: int, path: list[str], expected_root: str) -> bool:
    """Whether `path` shows the line with `line_hash` at `index` of a batch of `size` lines under `expected_root`
    (RFC 9162 2.1.3.2)."""
    if not 0 <= index < size:
        return False
    fn, sn = index, size - 1
    r = leaf(line_hash)
    for step in path:
        if sn == 0:
            return False
        p = bytes.fromhex(step)
        if fn % 2 == 1 or fn == sn:
            r = node(p, r)
            if fn % 2 == 0:
                while fn % 2 == 0 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r.hex() == expected_root
