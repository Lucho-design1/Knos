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
