"""The committed Groth16 fixture (zk/fixtures/score64, made by zk/score_circuit) verifies with the pure-Python BN254
checker, every tampered form is refused, and the public inputs are the commitments of the SYNTHETIC sample.

Runs without the Rust toolchain: only the small JSON fixtures are read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knos.zk import bn254, groth16, mimc

FIX = Path(__file__).resolve().parents[1] / "zk" / "fixtures" / "score64"


@pytest.fixture(scope="module")
def fx():
    return groth16.load_dir(FIX)


def _flip(b: bytes, i: int) -> bytes:
    out = bytearray(b)
    out[i] ^= 1
    return bytes(out)


def test_pairing_is_bilinear_and_nondegenerate():
    e = bn254.pairing(bn254.G1_GEN, bn254.G2_GEN)
    assert e != bn254.F12_ONE
    assert bn254.pairing(bn254.g1_mul(bn254.G1_GEN, 3), bn254.G2_GEN) == bn254.pairing(bn254.G1_GEN, bn254.g2_mul(bn254.G2_GEN, 3))


def test_fixture_proof_verifies(fx):
    vk, proof, inputs = fx
    assert groth16.verify(vk, proof, inputs)


@pytest.mark.parametrize("part,byte", [("a", 63), ("b", 127), ("c", 63), ("a", 10), ("c", 40)])
def test_tampered_proof_is_refused(fx, part, byte):
    vk, proof, inputs = fx
    bad = groth16.Proof(**{**proof.__dict__, part: _flip(getattr(proof, part), byte)})
    assert not groth16.verify(vk, bad, inputs)


@pytest.mark.parametrize("which", [0, 1, 2])
def test_tampered_public_input_is_refused(fx, which):
    vk, proof, inputs = fx
    bad = list(inputs)
    bad[which] ^= 1  # another spec, another submission, a lower bar (48 -> 49 is also not what was proven)
    assert not groth16.verify(vk, proof, bad)


def test_lower_bar_claim_is_refused(fx):
    vk, proof, inputs = fx
    assert not groth16.verify(vk, proof, [inputs[0], inputs[1], inputs[2] - 1])


def test_input_at_group_order_and_wrong_count_are_refused(fx):
    vk, proof, inputs = fx
    assert not groth16.verify(vk, proof, [bn254.R, inputs[1], inputs[2]])
    assert not groth16.verify(vk, proof, inputs[:2])


def test_negated_a_and_swapped_points_are_refused(fx):
    vk, proof, inputs = fx
    assert not groth16.verify(vk, groth16.Proof(proof.a_negated(), proof.b, proof.c), inputs)
    assert not groth16.verify(vk, groth16.Proof(proof.c, proof.b, proof.a), inputs)


def test_off_curve_points_are_false_not_errors(fx):
    vk, proof, inputs = fx
    junk = groth16.Proof(bytes(range(64)), proof.b, proof.c)
    assert not groth16.verify(vk, junk, inputs)
    with pytest.raises(ValueError):
        bn254.g2_from_bytes(bytes([1]) * 128)


def test_public_inputs_are_the_commitments_of_the_synthetic_sample():
    sample = json.loads((FIX / "sample.json").read_text())
    assert "SYNTHETIC" in sample
    pub = groth16.inputs_from_json(json.loads((FIX / "public.json").read_text()))
    assert pub[0] == mimc.spec_hash(sample["labels"], int(sample["spec_salt"], 16))
    assert pub[1] == mimc.pred_hash(sample["preds"], int(sample["pred_salt"], 16))
    assert pub[2] == sample["threshold"] == 48
    assert sum(a == b for a, b in zip(sample["labels"], sample["preds"])) == sample["correct"] == 52
    # the salt is what hides a small label set: another salt, another commitment
    assert mimc.spec_hash(sample["labels"], 1) != pub[0]


def test_toy_setup_is_labelled():
    vk = json.loads((FIX / "vk.json").read_text())
    assert "TOY" in vk["setup"] and "NOT a ceremony" in vk["setup"]
