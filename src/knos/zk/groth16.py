"""Groth16 over BN254: read a verifying key, a proof and public inputs (the JSON zk/score_circuit writes) and check
them off chain with the same equation the knos_zk program asks the alt_bn128 pairing syscall:

  e(-A, B) * e(L, gamma) * e(C, delta) * e(alpha, beta) == 1,   L = IC_0 + sum_i input_i * IC_{i+1}

Every input must be below the group order r, as groth16-solana's `verify` requires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import bn254


@dataclass(frozen=True)
class VerifyingKey:
    alpha: tuple
    beta: tuple
    gamma: tuple
    delta: tuple
    ic: tuple

    @classmethod
    def from_json(cls, doc: dict) -> "VerifyingKey":
        h = bytes.fromhex
        return cls(
            alpha=bn254.g1_from_bytes(h(doc["alpha_g1"])),
            beta=bn254.g2_from_bytes(h(doc["beta_g2"])),
            gamma=bn254.g2_from_bytes(h(doc["gamma_g2"])),
            delta=bn254.g2_from_bytes(h(doc["delta_g2"])),
            ic=tuple(bn254.g1_from_bytes(h(p)) for p in doc["ic"]),
        )


@dataclass(frozen=True)
class Proof:
    a: bytes  # 64, as proven (not negated)
    b: bytes  # 128
    c: bytes  # 64

    @classmethod
    def from_json(cls, doc: dict) -> "Proof":
        p = cls(bytes.fromhex(doc["a"]), bytes.fromhex(doc["b"]), bytes.fromhex(doc["c"]))
        if (len(p.a), len(p.b), len(p.c)) != (64, 128, 64):
            raise ValueError("a proof is A 64 bytes, B 128, C 64")
        return p

    def a_negated(self) -> bytes:
        """A with y -> q - y: what the program reads"""
        return bn254.g1_to_bytes(bn254.g1_neg(bn254.g1_from_bytes(self.a)))


def inputs_from_json(doc: dict) -> list[int]:
    return [int(x, 16) for x in doc["inputs"]]


def verify(vk: VerifyingKey, proof: Proof, inputs: list[int]) -> bool:
    """True only for a valid proof of these inputs under this key; a malformed point is False, never an exception"""
    if len(inputs) + 1 != len(vk.ic):
        return False
    if any(not 0 <= x < bn254.R for x in inputs):
        return False
    try:
        a = bn254.g1_from_bytes(proof.a)
        b = bn254.g2_from_bytes(proof.b)
        c = bn254.g1_from_bytes(proof.c)
    except ValueError:
        return False
    acc = vk.ic[0]
    for x, pt in zip(inputs, vk.ic[1:]):
        acc = bn254.g1_add(acc, bn254.g1_mul(pt, x))
    return bn254.pairing_product_is_one(
        [(bn254.g1_neg(a), b), (acc, vk.gamma), (c, vk.delta), (vk.alpha, vk.beta)]
    )


def load_dir(path: str | Path) -> tuple[VerifyingKey, Proof, list[int]]:
    """vk.json, proof.json, public.json of one fixture/proof directory"""
    d = Path(path)
    read = lambda n: json.loads((d / n).read_text())  # noqa: E731
    return VerifyingKey.from_json(read("vk.json")), Proof.from_json(read("proof.json")), inputs_from_json(read("public.json"))
