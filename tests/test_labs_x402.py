"""Paying a lab over x402 on Base (testnet: Base Sepolia) and on Solana devnet: payloads built and checked offline."""
from __future__ import annotations

import hashlib

import pytest

from knos.labs import evm, x402pay


def test_keccak_and_secp256k1_match_published_vectors():
    assert evm.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert evm.address((1).to_bytes(32, "big")) == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
    # EIP-712's own example domain ("Ether Mail")
    assert evm.domain_separator("Ether Mail", "1", 1, "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC").hex() == \
        "f2cee375fa42b42143804025fc449deafd50cc031ca257e0b194a650a912090f"
    for i in range(8):
        k, h = hashlib.sha256(bytes([i])).digest(), hashlib.sha256(b"m" + bytes([i])).digest()
        s = evm.sign_hash(k, h)
        assert evm.recover(h, s) == evm.address(k) and int.from_bytes(s[32:64], "big") <= evm.N // 2


def test_the_x402_specs_own_signed_example_recovers_to_its_from_address():
    """specs/schemes/exact/scheme_exact_evm.md (coinbase/x402): the example PaymentPayload on Base Sepolia."""
    auth = {"from": "0x857b06519E91e3A54538791bDbb0E22373e36b66", "to": "0x209693Bc6afc0C5328bA36FaF03C514EF312287C", "value": "10000",
            "validAfter": "1740672089", "validBefore": "1740672154",
            "nonce": "0xf3746613c2d920b5fdabc0856f2aeb2d4f88ee6037b8cc5d04a71a4462f13480"}
    sig = bytes.fromhex("2d6a7588d6acca505cbf0d9a4a227e0c52c6c34008c8e8986a1283259764173608a2ce6496642e377d6da8dbbf5836e9bd15092f9ecab05ded3d6293af148b571c")
    h = evm.transfer_with_authorization_hash(auth, name="USDC", version="2", chain_id=84532, contract=x402pay.USDC[x402pay.BASE_SEPOLIA])
    assert evm.recover(h, sig) == auth["from"]


REQ = {"scheme": "exact", "network": x402pay.BASE_SEPOLIA, "amount": "1060000000", "payTo": "0x000000000000000000000000000000000000dEaD",
       "asset": x402pay.USDC[x402pay.BASE_SEPOLIA], "maxTimeoutSeconds": 300, "extra": {"name": "USDC", "version": "2", "assetTransferMethod": "eip3009"}}
KEY = hashlib.sha256(b"knos labs test").digest()


def test_a_payload_pays_exactly_the_lab_and_any_change_is_caught():
    p = x402pay.evm_payload(REQ, KEY, now=1_800_000_000)
    assert x402pay.check_evm(p, REQ, now=1_800_000_000) == []
    assert p["payload"]["authorization"]["from"] == evm.address(KEY)
    worse = dict(p, payload=dict(p["payload"], authorization=dict(p["payload"]["authorization"], to="0x" + "11" * 20)))
    assert any("another address" in w for w in x402pay.check_evm(worse, REQ, now=1_800_000_000))
    more = dict(p, payload=dict(p["payload"], authorization=dict(p["payload"]["authorization"], value="1")))
    assert any("another amount" in w for w in x402pay.check_evm(more, REQ, now=1_800_000_000))
    assert any("validity window" in w for w in x402pay.check_evm(p, REQ, now=1_900_000_000))


def test_header_round_trip_and_v1_bodies():
    ch = {"x402Version": 2, "resource": {"url": "u"}, "accepts": [REQ]}
    assert x402pay.decode_challenge({"payment-required": x402pay.challenge_header(ch)}) == ch
    assert x402pay.decode_challenge({}, {"accepts": [REQ]})["accepts"] == [REQ]
    with pytest.raises(x402pay.PayError):
        x402pay.decode_challenge({}, {})


def test_knos_pays_only_on_testnets_until_mainnet_is_approved():
    main = dict(REQ, network=x402pay.BASE, asset=x402pay.USDC[x402pay.BASE])
    with pytest.raises(x402pay.PayError, match="only on"):
        x402pay.choose([main])
    assert x402pay.choose([main, REQ]) == REQ


def test_the_same_lab_invoice_on_solana_devnet_builds_an_exact_transfer():
    from solders.hash import Hash
    from solders.keypair import Keypair
    payer, lab, fee = Keypair(), Keypair(), Keypair()
    req = {"scheme": "exact", "network": x402pay.SOLANA_DEVNET, "amount": "5000000", "asset": str(Keypair().pubkey()), "payTo": str(lab.pubkey()),
           "maxTimeoutSeconds": 60, "extra": {"feePayer": str(fee.pubkey())}}
    p = x402pay.solana_payload(req, payer, Hash.default(), decimals=6)
    assert p["x402Version"] == 2 and p["accepted"] == req and p["payload"]["transaction"]
