"""The knos_zk instructions, verdict account and payout rule, from Python, against the committed fixtures; the
program's compiled-in verifying key is the fixture key. No toolchain, no network."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from solders.pubkey import Pubkey

from knos.zk import bn254, client, groth16, mimc

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "zk" / "fixtures" / "score64"
PROGRAM = Pubkey.from_string(client.DEVNET_PROGRAM_ID)


@pytest.fixture(scope="module")
def fx():
    return groth16.load_dir(FIX)


def test_verify_instruction_layout(fx):
    _, proof, inputs = fx
    ix = client.verify_ix(PROGRAM, proof, inputs)
    data = bytes(ix.data)
    assert len(data) == 1 + 256 + 96 and data[0] == 0 and not ix.accounts
    a = bn254.g1_from_bytes(proof.a)
    assert bn254.g1_from_bytes(data[1:65]) == bn254.g1_neg(a)  # A negated, x kept
    assert data[1:33] == proof.a[:32]
    assert data[65:193] == proof.b and data[193:257] == proof.c
    assert [int.from_bytes(data[257 + 32 * i:289 + 32 * i], "big") for i in range(3)] == inputs


def test_record_instruction_and_verdict_address(fx):
    _, proof, inputs = fx
    payer = Pubkey.new_unique()
    ix = client.record_ix(PROGRAM, payer, proof, inputs)
    data = bytes(ix.data)
    verdict, bump = client.verdict_address(PROGRAM, inputs)
    assert data[:2] == bytes([1, bump]) and len(data) == 2 + 352
    assert [m.pubkey for m in ix.accounts] == [payer, verdict, client.SYSTEM_PROGRAM]
    assert ix.accounts[0].is_signer and ix.accounts[1].is_writable and not ix.accounts[1].is_signer
    raw = client.inputs_bytes(inputs)
    assert Pubkey.create_program_address([b"verdict", raw[:32], raw[32:64], raw[94:96], bytes([bump])], PROGRAM) == verdict
    # another bar, another verdict account
    assert client.verdict_address(PROGRAM, [inputs[0], inputs[1], 40])[0] != verdict


def test_inputs_must_be_three_field_elements(fx):
    _, proof, inputs = fx
    with pytest.raises(ValueError):
        client.verify_ix(PROGRAM, proof, inputs[:2])
    with pytest.raises(ValueError):
        client.verify_ix(PROGRAM, proof, [bn254.R, inputs[1], inputs[2]])


def _verdict_bytes(inputs, slot=7, recorder=None) -> bytes:
    recorder = recorder or Pubkey.new_unique()
    return bytes([1, 255]) + client.inputs_bytes(inputs) + slot.to_bytes(8, "little") + bytes(recorder)


def test_payout_rule_reads_the_verdict(fx):
    _, _, inputs = fx
    data = _verdict_bytes(inputs)
    v = client.parse_verdict(data)
    assert (v.spec_hash, v.pred_hash, v.threshold, v.slot) == (inputs[0], inputs[1], 48, 7)
    ok, why = client.payable(PROGRAM, data, PROGRAM, spec_hash=inputs[0], bar=48, pred_hash=inputs[1])
    assert ok and not why
    assert client.payable(PROGRAM, data, PROGRAM, spec_hash=inputs[0], bar=40)[0]  # a lower bar is met by 48
    assert not client.payable(PROGRAM, data, PROGRAM, spec_hash=inputs[0], bar=49)[0]
    assert not client.payable(PROGRAM, data, PROGRAM, spec_hash=inputs[0] ^ 1, bar=48)[0]
    assert not client.payable(PROGRAM, data, PROGRAM, spec_hash=inputs[0], bar=48, pred_hash=inputs[1] ^ 1)[0]
    # an account the program does not own was not made by a verified proof, whatever it holds
    assert not client.payable(Pubkey.new_unique(), data, PROGRAM, spec_hash=inputs[0], bar=48)[0]
    assert not client.payable(PROGRAM, data[:-1], PROGRAM, spec_hash=inputs[0], bar=48)[0]


def test_statement_never_needs_more_than_the_hashes():
    sample = json.loads((FIX / "sample.json").read_text())
    s, p = int(sample["spec_salt"], 16), int(sample["pred_salt"], 16)
    st = client.statement(sample["labels"], s, sample["preds"], p, 48)
    assert st["provable"] and st["inputs"] == groth16.inputs_from_json(json.loads((FIX / "public.json").read_text()))
    assert not client.statement(sample["labels"], s, sample["preds"], p, 53)["provable"]  # 52 right: below the bar
    assert 0 < mimc.new_salt() < bn254.R


def test_program_embeds_the_fixture_key():
    """programs-v2/knos_zk/src/vk.rs (generated) holds the same key as zk/fixtures/score64/vk.json"""
    text = (ROOT / "programs-v2" / "knos_zk" / "src" / "vk.rs").read_text()
    arrays = [bytes(int(x) for x in m.split(",")) for m in re.findall(r"\[([0-9,]+)\]", text)]
    vk = json.loads((FIX / "vk.json").read_text())
    want = [vk["alpha_g1"], vk["beta_g2"], vk["gamma_g2"], vk["delta_g2"], *vk["ic"]]
    assert [a.hex() for a in arrays] == want
    assert "nr_pubinputs: 3" in text


def test_measured_compute_units_are_recorded():
    if not (FIX / "cu.json").exists():
        pytest.skip("cu.json is written by zk/litesvm_cu (LiteSVM run of the built program); not measured in this tree yet")
    cu = json.loads((FIX / "cu.json").read_text())
    assert 0 < cu["verify_cu"] < 1_400_000
    assert cu["verify_cu"] < cu["verify_and_record_cu"] < 1_400_000


def test_devnet_receipt_is_public_and_consistent():
    if not (FIX / "devnet.json").exists():
        pytest.skip("the devnet deploy waits for devnet SOL on the ZK deployer (docs/reference/ZK.md, Where it runs)")
    doc = json.loads((FIX / "devnet.json").read_text())
    assert doc["cluster"] == "devnet" and doc["program_id"] == client.DEVNET_PROGRAM_ID and "SYNTHETIC" in doc
    b58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{80,90}$")
    runs = doc["runs"]
    assert runs["verify"]["err"] is None and 0 < runs["verify"]["compute_units"] < 1_400_000
    for k in ("tampered_threshold", "tampered_proof_c"):
        assert runs[k]["err"] is not None, k  # landed on chain and was refused
    for r in runs.values():
        assert b58.match(r["signature"])
    assert doc["payable"] is True
    text = json.dumps(doc).lower()
    assert "secret" not in text and "private_key" not in text


def test_command_line_verifies_and_refuses(tmp_path, capsys):
    from knos.zk.__main__ import main

    assert main(["verify", str(FIX)]) == 0
    for name in ("vk.json", "public.json"):
        (tmp_path / name).write_text((FIX / name).read_text())
    proof = json.loads((FIX / "proof.json").read_text())
    proof["c"], proof["a"] = proof["a"], proof["c"]
    (tmp_path / "proof.json").write_text(json.dumps(proof))
    assert main(["verify", str(tmp_path)]) == 1
    assert main(["ix", str(FIX), client.DEVNET_PROGRAM_ID]) == 0
    assert main([]) == 2
