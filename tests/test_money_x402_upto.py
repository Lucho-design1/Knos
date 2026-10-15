"""x402 `upto` on Solana through the payment-channels program (knos.money.x402_upto). Instruction bytes are checked
against the program's own layouts; keys are made in the test (synthetic); no network."""
from __future__ import annotations

import hashlib

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature

from knos.money import x402_upto as u

T22 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")


def parties():
    return {k: Keypair() for k in ("payer", "payee", "lab", "auth")}, Keypair().pubkey()


def test_the_voucher_and_its_ed25519_instruction_are_in_the_canonical_layout():
    p, _mint = parties()
    ch = Keypair().pubkey()
    v = u.voucher(ch, 7_000_000)
    assert len(v) == 50 and v[:2] == bytes([0x56, 0x01]) and v[2:34] == bytes(ch) and int.from_bytes(v[34:42], "little") == 7_000_000
    ix = u.ed25519_ix(p["auth"], v)
    d = bytes(ix.data)
    assert ix.program_id == u.ED25519 and d[:2] == b"\x01\x00" and len(d) == 112 + 50
    offs = [int.from_bytes(d[2 + 2 * i:4 + 2 * i], "little") for i in range(7)]
    assert offs == [48, 0xFFFF, 16, 0xFFFF, 112, 50, 0xFFFF]
    assert d[16:48] == bytes(p["auth"].pubkey()) and d[112:] == v
    assert Signature.from_bytes(d[48:112]).verify(p["auth"].pubkey(), v)


def test_open_is_read_back_from_its_bytes_and_checked_against_the_402():
    p, mint = parties()
    splits = [(p["lab"].pubkey(), 1_000)]
    req = u.requirements(ceiling=20_000_000, mint=mint, pay_to=p["payee"].pubkey(), receiver_authorizer=p["auth"].pubkey(), decimals=6,
                         resource="https://example.invalid/checks (synthetic)", splits=splits, token_program=T22)
    assert req["scheme"] == "upto" and req["network"].startswith("solana:") and req["amount"] == "20000000"
    ix = u.open_ix(p["payer"].pubkey(), p["payer"].pubkey(), p["payee"].pubkey(), mint, p["auth"].pubkey(), 42, 20_000_000, 900, 1234, splits, T22)
    assert bytes(ix.data)[0] == 1 and len(ix.accounts) == 14 and ix.accounts[0].is_signer and ix.accounts[1].is_signer
    got = u.read_open(bytes(ix.data), [a.pubkey for a in ix.accounts])
    assert got.deposit == 20_000_000 and got.open_slot == 1234 and got.splits == splits and u.check_open(got, req) == []
    # a payer who changes anything the server asked for is refused before the server signs or pays for anything
    bad = u.open_ix(p["payer"].pubkey(), p["payer"].pubkey(), p["payee"].pubkey(), mint, p["payer"].pubkey(), 42, 1, 1, 1234, [], T22)
    why = u.check_open(u.read_open(bytes(bad.data), [a.pubkey for a in bad.accounts]), req)
    assert any("signer" in w for w in why) and any("grace" in w for w in why) and any("splits" in w for w in why) and any("ceiling" in w for w in why)


def test_splits_follow_the_programs_rules():
    a, b = Keypair().pubkey(), Keypair().pubkey()
    assert u.splits_bytes([]) == b"\x00\x00\x00\x00" and len(u.splits_bytes([(a, 1), (b, 2)])) == 4 + 68
    for bad in ([(a, 0)], [(a, 6000), (b, 5000)], [(a, 1), (a, 2)], [(Keypair().pubkey(), 1) for _ in range(33)]):
        with pytest.raises(ValueError):
            u.splits_bytes(bad)


def channel_bytes(payer, payee, signer, mint, rent_payer, deposit, settled, splits, status=0) -> bytes:
    d = bytearray(256)
    d[0], d[1], d[3] = 1, 1, status
    d[12:20], d[20:28] = deposit.to_bytes(8, "little"), settled.to_bytes(8, "little")
    d[56:88] = hashlib.sha256(u.splits_bytes(splits)).digest()
    for at, k in ((88, payer), (120, payee), (152, signer), (184, mint), (216, rent_payer)):
        d[at:at + 32] = bytes(k)
    return bytes(d)


def test_settlement_is_one_transaction_and_never_more_than_the_ceiling():
    p, mint = parties()
    splits = [(p["lab"].pubkey(), 1_000)]
    raw = channel_bytes(p["payer"].pubkey(), p["payee"].pubkey(), p["auth"].pubkey(), mint, p["payer"].pubkey(), 20_000_000, 0, splits)
    ch = u.read_channel(raw)
    assert ch.status == "open" and ch.deposit == 20_000_000 and ch.signer == p["auth"].pubkey()
    addr = Keypair().pubkey()
    ixs = u.settle_ixs(p["auth"], p["payee"].pubkey(), ch, addr, 7_000_000, splits, "devnet", T22)
    assert [ix.program_id for ix in ixs] == [u.ED25519, u.PROGRAM, u.PROGRAM]
    assert bytes(ixs[1].data) == b"\x04\x01" and bytes(ixs[2].data)[0] == 7 and len(ixs[2].accounts) == 11 + 1
    assert ixs[2].accounts[6].pubkey == u.ata(u.TREASURY_OWNER["devnet"], mint, T22)
    with pytest.raises(ValueError, match="ceiling"):
        u.settle_ixs(p["auth"], p["payee"].pubkey(), ch, addr, 20_000_001, splits)
    with pytest.raises(ValueError, match="splits"):
        u.settle_ixs(p["auth"], p["payee"].pubkey(), ch, addr, 1, [(p["payee"].pubkey(), 1)])
    zero = u.settle_ixs(p["auth"], p["payee"].pubkey(), ch, addr, 0, splits)      # nothing used: seal with no voucher, refund all
    assert bytes(zero[0].data) == b"\x04\x00" and len(zero) == 2
    resp = u.response("sig", "devnet", 7_000_000, 20_000_000, p["payer"].pubkey())
    assert resp["amount"] == "7000000" and resp["refunded"] == "13000000"


def test_the_channel_address_binds_every_seed():
    p, mint = parties()
    a = u.channel_pda(p["payer"].pubkey(), p["payee"].pubkey(), mint, p["auth"].pubkey(), 1, 100)
    assert a != u.channel_pda(p["payer"].pubkey(), p["payee"].pubkey(), mint, p["auth"].pubkey(), 1, 101)
    assert a != u.channel_pda(p["payer"].pubkey(), p["payee"].pubkey(), mint, p["auth"].pubkey(), 2, 100)
    assert str(u.PROGRAM) == "CHNLxYvVA28MJP9PrFuDXccuoGXAx7jBacfLEkahyGsX" and u.read_channel(b"\x00" * 10) is None
