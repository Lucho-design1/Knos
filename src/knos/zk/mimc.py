"""The commitment hash of the private-score circuit (zk/score_circuit/src/lib.rs computes the same, in and out of the
circuit): MiMC-7 over the BN254 scalar field, 91 rounds, chained as circomlib's MultiMiMC7.

  c_0 = 0, c_i = sha256("knos-zk-mimc7:" || i as 4 bytes big-endian) mod r
  MiMC7(x, k): repeat 91 times x = (x + k + c_i)^7; return x + k
  H(domain, salt, xs): r = 0; for e in [domain, salt, *xs]: r = r + e + MiMC7(e, r)

spec_hash = H(1, spec_salt, labels); pred_hash = H(2, pred_salt, predictions). A salt is a whole field element, so a
small set of labels cannot be found by hashing every candidate set.
"""

from __future__ import annotations

import hashlib
import secrets
from functools import lru_cache

from .bn254 import R

ROUNDS = 91
DOMAIN_SPEC = 1
DOMAIN_PRED = 2


@lru_cache(maxsize=1)
def constants() -> tuple[int, ...]:
    out = [0]
    for i in range(1, ROUNDS):
        out.append(int.from_bytes(hashlib.sha256(b"knos-zk-mimc7:" + i.to_bytes(4, "big")).digest(), "big") % R)
    return tuple(out)


def mimc7(x: int, k: int) -> int:
    for c in constants():
        t = (x + k + c) % R
        x = pow(t, 7, R)
    return (x + k) % R


def multi_mimc(domain: int, salt: int, xs) -> int:
    r = 0
    for e in [domain, salt, *xs]:
        e %= R
        r = (r + e + mimc7(e, r)) % R
    return r


def spec_hash(labels, salt: int) -> int:
    return multi_mimc(DOMAIN_SPEC, salt, labels)


def pred_hash(preds, salt: int) -> int:
    return multi_mimc(DOMAIN_PRED, salt, preds)


def new_salt() -> int:
    """a fresh salt: 32 random bytes reduced into the field"""
    return int.from_bytes(secrets.token_bytes(32), "big") % R
