"""knos_wanted.chainx in LiteSVM (Token-2022, the ATA program and Memo are built in): a project's group mint, a
milestone's non-transferable badge with on-mint metadata in that group, minted to the maker; a release memo."""
import types

import pytest
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from knos_wanted import chainx


class Ledger:
    url = "http://litesvm"

    def __init__(self):
        self.svm = LiteSVM()

    def rent(self, n):
        return self.svm.minimum_balance_for_rent_exemption(n)

    def account(self, a):
        x = self.svm.get_account(a if isinstance(a, Pubkey) else Pubkey.from_string(str(a)))
        return bytes(x.data) if x else None

    def send(self, ixs, payer, signers=None):
        tx = Transaction(list({str(s.pubkey()): s for s in [payer, *(signers or [])]}.values()),
                         Message.new_with_blockhash(list(ixs), payer.pubkey(), self.svm.latest_blockhash()), self.svm.latest_blockhash())
        r = self.svm.send_transaction(tx)
        assert not hasattr(r, "err"), r
        return str(tx.signatures[0])

    def send_all(self, groups, payer, signers=None):
        return [self.send(g, payer, signers) for g in groups]


@pytest.fixture
def chain(monkeypatch, tmp_path):
    from knos_wanted import escrow, preorder
    led = Ledger()
    payer = Keypair()
    led.svm.airdrop(payer.pubkey(), 10_000_000_000)
    monkeypatch.setattr(preorder, "relayer", lambda: payer)
    monkeypatch.setattr(escrow, "_state_dir", lambda: tmp_path)
    return types.SimpleNamespace(led=led, payer=payer)


def test_a_badge_is_non_transferable_has_its_metadata_and_is_a_member_of_the_project_group(chain):
    mk = Keypair()
    maker = mk.pubkey()
    b = chainx.badge("p" * 16, "Sweat glucose watch", "assay", "Glucose assay on 12 samples", str(maker), "https://knos.onrender.com/#projects=pppp",
                     led=chain.led)
    mint = chain.led.account(b["mint"])
    assert b"Knos: Glucose assay on 12 sampl" in mint and b"KNOSV" in mint            # TokenMetadata on the mint itself
    acct = chain.led.account(b["account"])
    assert int.from_bytes(acct[64:72], "little") == 1 and acct[32:64] == bytes(maker)    # one badge, owned by the maker
    group = chain.led.account(b["group"])
    assert group and len(group) > chainx.BASE                                            # the project's group mint
    assert chainx.badge("p" * 16, "x", "assay", "x", str(maker), "u", led=chain.led)["mint"] == b["mint"]   # once per milestone and maker
    other = Keypair()
    chain.led.svm.airdrop(other.pubkey(), 1_000_000_000)
    from solders.instruction import AccountMeta, Instruction
    dest = chainx._ata(other.pubkey(), Pubkey.from_string(b["mint"]))
    chain.led.send([Instruction(Pubkey.from_string(chainx.ATA), bytes([1]), [AccountMeta(other.pubkey(), True, True), AccountMeta(dest, False, True),
                   AccountMeta(other.pubkey(), False, False), AccountMeta(Pubkey.from_string(b['mint']), False, False),
                   AccountMeta(Pubkey.from_string(chainx.SYSTEM), False, False), AccountMeta(Pubkey.from_string(chainx.TOKEN22), False, False)])], other)
    assert chain.led.account(dest)                                                     # the recipient's account exists
    with pytest.raises(AssertionError):                                                  # NonTransferable: a transfer fails
        chain.led.send([Instruction(Pubkey.from_string(chainx.TOKEN22), bytes([12]) + (1).to_bytes(8, "little") + bytes([0]),
                                    [AccountMeta(Pubkey.from_string(b["account"]), False, True), AccountMeta(Pubkey.from_string(b["mint"]), False, False),
                                     AccountMeta(dest, False, True), AccountMeta(maker, True, False)])], other, [mk])


def test_a_release_memo_is_sent_and_the_tree_size_matches_the_program(chain):
    assert chainx.memo("knos release abc brief sha256:" + "a" * 64, led=chain.led)
    assert chainx.tree_size(14, 64) == 56 + 24 + 64 * (32 + 32 * 14 + 8) + (32 * 14 + 40)


EVM = {"address": "0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a", "message": "knos lab result: 12 samples within 4% of the blood reference",
       "signature": "755bd97eddcac667515a8cba4896af572aa42aa1d821f4437c65d09dd071707c333bea0ad141f25bd9a634f48925aea22e35ddcbe359a88db48fb2ccf68204941b"}


def test_an_evm_signed_attestation_is_checked_by_the_secp256k1_precompile(chain):
    # signed by eth_account with the fixed test key 0x11..11 over keccak256(message): the precompile recovers its signer
    got = chainx.evm_verify(EVM["address"], EVM["signature"], EVM["message"], led=chain.led)
    assert got["verified"] and got["signer"] == EVM["address"]
    with pytest.raises(AssertionError):                                     # another signer: the transaction fails
        chainx.evm_verify("0x" + "22" * 20, EVM["signature"], EVM["message"], led=chain.led)
    with pytest.raises(AssertionError):                                     # another message: the transaction fails
        chainx.evm_verify(EVM["address"], EVM["signature"], EVM["message"] + ".", led=chain.led)


def test_lookup_tables_are_frozen_or_deactivated_then_closed_with_their_rent_returned(chain):
    from solders.account import Account
    svm, payer = chain.led.svm, chain.payer
    svm.warp_to_slot(100)

    def table(n_addrs: int = 3):
        # a lookup table in the program's own layout: LookupTable tag 1, deactivation slot u64::MAX, last extended slot,
        # its start index, the authority (Some), 2 bytes of padding, then the addresses from byte 56
        t = Keypair().pubkey()
        data = (1).to_bytes(4, "little") + (2**64 - 1).to_bytes(8, "little") + (90).to_bytes(8, "little") + bytes([0]) + bytes([1]) + bytes(payer.pubkey())
        data += bytes(56 - len(data)) + b"".join(bytes(Keypair().pubkey()) for _ in range(n_addrs))
        svm.set_account(t, Account(lamports=chain.led.rent(len(data)), data=data, owner=Pubkey.from_string(chainx.ALT), executable=False))
        return t

    frozen, t = table(), table()
    chain.led.send([chainx.alt_ix(chainx.ALT_FREEZE, frozen, payer.pubkey())], payer)      # a wallet's table: frozen
    with pytest.raises(AssertionError):
        chain.led.send([chainx.alt_ix(chainx.ALT_DEACTIVATE, frozen, payer.pubkey())], payer)   # frozen for good
    chain.led.send([chainx.alt_ix(chainx.ALT_DEACTIVATE, t, payer.pubkey())], payer)      # a retired shared table
    assert int.from_bytes(chain.led.account(t)[4:12], "little") != 2**64 - 1                 # deactivated
    svm.warp_to_slot(700)                                                                   # past the deactivation cooldown
    before = svm.get_balance(payer.pubkey())
    chain.led.send([chainx.alt_ix(chainx.ALT_CLOSE, t, payer.pubkey(), payer.pubkey())], payer)
    assert chain.led.account(t) is None and svm.get_balance(payer.pubkey()) > before         # closed, rent back to the relayer


def test_a_pledge_receipt_needs_its_memo_stays_frozen_and_a_refund_burns_it_by_the_permanent_delegate(chain, monkeypatch):
    from solders.instruction import AccountMeta, Instruction

    from knos_wanted import escrow
    owner = Keypair()
    monkeypatch.setattr(escrow, "demo_key", lambda: owner)
    r = chainx.pledge_receipt("o" * 44, "knos:claim:abc", 10, led=chain.led)
    ledger = chain.led.account(r["ledger"])
    assert int.from_bytes(ledger[64:72], "little") == 10 * 10**6 and ledger[108] == 2      # 10 receipt units, frozen
    st = chainx._state("receipts")
    mint, inbox = Pubkey.from_string(r["receipt_mint"]), Pubkey.from_string(st["inbox"])
    t22 = Pubkey.from_string(chainx.TOKEN22)
    chain.led.send([Instruction(t22, bytes([7]) + (5).to_bytes(8, "little"), [AccountMeta(mint, False, True), AccountMeta(inbox, False, True),
                                                                             AccountMeta(chain.payer.pubkey(), True, False)]),
                    chainx._thaw(Pubkey.from_string(r["ledger"]), mint, chain.payer.pubkey())], chain.payer)
    with pytest.raises(AssertionError):                                       # RequiredMemoTransfers: no memo, no transfer in
        chain.led.send([Instruction(t22, bytes([12]) + (5).to_bytes(8, "little") + bytes([6]),
                                    [AccountMeta(inbox, False, True), AccountMeta(mint, False, False), AccountMeta(Pubkey.from_string(r["ledger"]), False, True),
                                     AccountMeta(chain.payer.pubkey(), True, False)])], chain.payer)
    chain.led.send([chainx._freeze(Pubkey.from_string(r["ledger"]), mint, chain.payer.pubkey())], chain.payer)
    burned = chainx.receipt_refund("o" * 44, led=chain.led)
    assert burned["burned"] and int.from_bytes(chain.led.account(r["ledger"])[64:72], "little") == 0     # burned by the delegate


def test_a_private_pledge_posts_the_encrypted_amount_and_its_proofs_which_the_zk_elgamal_program_verifies(chain):
    import base64
    import json
    from pathlib import Path
    fx = json.loads((Path(__file__).parent / "data" / "private_pledge.json").read_text(encoding="utf-8"))    # @solana/zk-sdk 0.5.4
    ct, pv, rp = (base64.b64decode(fx[k]) for k in ("ciphertext", "pubkey_proof", "range_proof"))
    got = chainx.private_pledge("order1", ct, pv, rp, led=chain.led)
    assert got["pubkey_signature"] and got["range_signature"] and got["ciphertext"] == fx["ciphertext"]
    assert not {"units", "amount"} & set(got)                                                          # the amount is not in the clear
    bad = bytearray(rp)
    bad[-1] ^= 1                                                                                       # a false proof: the program refuses it
    with pytest.raises(AssertionError):
        chainx.private_pledge("order2", ct, pv, bytes(bad), led=chain.led)
    with pytest.raises(ValueError, match="commitment"):                                                # a proof about another ciphertext
        chainx.private_pledge("order3", bytes(32) + ct[32:], pv, rp, led=chain.led)
    with pytest.raises(ValueError, match="bytes"):
        chainx.private_pledge("order4", ct[:10], pv, rp, led=chain.led)
