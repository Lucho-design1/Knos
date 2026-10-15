"""Kora: a researcher or an agent holding no SOL still funds, submits and collects, because a Kora node pays the fee.

Kora is the Solana Foundation's fee relayer (github.com/solana-foundation/kora, read 14 Oct 2026). A Kora node is a
JSON-RPC 2.0 server over HTTP POST; transactions are base64. The methods Knos uses, from the repository's
`.claude/skills/kora-client/references/rpc-api.md` and the OpenAPI document `crates/lib/src/rpc_server/openapi/spec/combined_api.json`:
    getConfig               the node's fee payers, allowed programs and tokens, and which methods are on
    getPayerSigner          {signer_address, payment_address}: the fee payer to put in the message, and where fees go
    estimateTransactionFee  {transaction, fee_token?} -> {fee_in_lamports, fee_in_token?, signer_pubkey, payment_address}
    signTransaction         {transaction} -> {signed_transaction, signer_pubkey}: the user has signed already
    signAndSendTransaction  {transaction} -> {signature, signed_transaction, signer_pubkey}
(transferTransaction is deprecated as of Kora 2.2.0 and not used.) Audit status, from audits/AUDIT_STATUS.md: Runtime
Verification, audited through commit 8c592591 (report 19 Nov 2025); later commits are unaudited until a new review.

How Knos uses it: the message names Kora's signer as the fee payer, the researcher's wallet signs for its own money,
Kora checks the transaction against its own policy (allowed programs: knos_pay; allowed tokens: the order's mint) and
signs as fee payer. `gasless_ixs` adds the fee payment to Kora in the order's token when the node charges one. Knos
never runs Kora with Knos's keys here: the node is the operator's (KORA_RPC_URL). No Kora node was run for this
build: the releases on GitHub carry no binaries (14 Oct 2026), and building it needs the crates downloaded; the tests
use a stand-in server whose answers are shaped from the OpenAPI document above and labelled synthetic.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from dataclasses import dataclass

from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import MessageV1, TransactionConfig, to_bytes_versioned
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

ENV = "KORA_RPC_URL"


class KoraError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"Kora error {code}: {message}")
        self.code = code


@dataclass
class Kora:
    url: str
    api_key: str | None = None      # a node may require one (header x-api-key); KORA_API_KEY
    timeout: float = 20.0
    post = None                     # tests: post(url, body_bytes, headers) -> bytes

    @classmethod
    def from_env(cls) -> "Kora":
        url = os.environ.get(ENV)
        if not url:
            raise KoraError("config", f"set {ENV} to the Kora node's URL (no node is configured)")
        return cls(url, os.environ.get("KORA_API_KEY"))

    def call(self, method: str, params: dict | None = None):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
        headers = {"Content-Type": "application/json", **({"x-api-key": self.api_key} if self.api_key else {})}
        if self.post is not None:
            raw = self.post(self.url, body, headers)
        else:
            req = urllib.request.Request(self.url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - the operator's own Kora node
                raw = r.read()
        got = json.loads(raw)
        if "error" in got:
            err = got["error"]
            raise KoraError(err.get("code"), err.get("message"))
        return got["result"]

    def config(self) -> dict:
        return self.call("getConfig")

    def payer_signer(self) -> tuple[Pubkey, Pubkey]:
        got = self.call("getPayerSigner")
        return Pubkey.from_string(got["signer_address"]), Pubkey.from_string(got["payment_address"])

    def blockhash(self) -> Hash:
        return Hash.from_string(self.call("getBlockhash")["blockhash"])

    def estimate(self, tx_b64: str, fee_token: Pubkey | None = None) -> dict:
        return self.call("estimateTransactionFee", {"transaction": tx_b64, **({"fee_token": str(fee_token)} if fee_token else {})})

    def sign(self, tx_b64: str) -> str:
        return self.call("signTransaction", {"transaction": tx_b64})["signed_transaction"]

    def sign_and_send(self, tx_b64: str) -> str:
        return self.call("signAndSendTransaction", {"transaction": tx_b64})["signature"]


def policy_problems(config: dict, programs: list[Pubkey], mint: Pubkey | None = None) -> list[str]:
    """What the node's own policy would refuse in a Knos transaction: a program it does not allow, a token it does not
    take for fees, the signing methods turned off. Asked before the user signs anything."""
    v, on, out = config.get("validation_config", {}), config.get("enabled_methods", {}), []
    allowed = set(v.get("allowed_programs") or [])
    out += [f"the node does not allow program {p}" for p in programs if allowed and str(p) not in allowed]
    paid = set(v.get("allowed_spl_paid_tokens") or [])
    if mint is not None and paid and str(mint) not in paid:
        out.append(f"the node takes no fees in {mint}")
    if not (on.get("sign_transaction") or on.get("sign_and_send_transaction")):
        out.append("the node has signing turned off")
    return out


def message(ixs: list[Instruction], fee_payer: Pubkey, blockhash: Hash, units: int = 1_400_000, v1: bool = True):
    """A message with Kora's signer as fee payer: the user's wallet signs as an ordinary signer, never pays SOL. v1 by
    default; `v1=False` gives a legacy message for a node whose version does not decode v1 (Kora's docs do not say)."""
    if not v1:
        from solders.message import Message
        return Message.new_with_blockhash(list(ixs), fee_payer, blockhash)
    return MessageV1.try_compile(fee_payer, list(ixs), blockhash,
                                 TransactionConfig(compute_unit_limit=units, loaded_accounts_data_size_limit=64 * 1024 * 1024, priority_fee=None))


def user_signed(msg, users: list[Keypair]) -> str:
    """The transaction, signed by the users only (the fee payer's slot left blank for Kora), as base64."""
    keys = list(msg.account_keys[:msg.header.num_required_signatures])
    raw = to_bytes_versioned(msg) if isinstance(msg, MessageV1) else bytes(msg)
    mine = {u.pubkey(): u for u in users}
    sigs = [mine[k].sign_message(raw) if k in mine else Signature.default() for k in keys]
    return base64.b64encode(bytes(VersionedTransaction.populate(msg, sigs))).decode()


def gasless_ixs(ixs: list[Instruction], kora: Kora, user: Pubkey, user_token: Pubkey, mint: Pubkey, decimals: int, fee_units: int,
                token_program: Pubkey) -> list[Instruction]:
    """`ixs` with the fee paid to Kora's payment address in the order's token (TransferChecked), when the node charges
    `fee_units` (> 0) of it. Kora's estimate says how much (estimateTransactionFee with fee_token)."""
    if fee_units <= 0:
        return list(ixs)
    from .x402_upto import ata
    _signer, pay_to = kora.payer_signer()
    data = bytes([12]) + fee_units.to_bytes(8, "little") + bytes([decimals])    # TransferChecked
    from solders.instruction import AccountMeta
    fee = Instruction(token_program, data, [AccountMeta(user_token, False, True), AccountMeta(mint, False, False),
                                            AccountMeta(ata(pay_to, mint, token_program), False, True), AccountMeta(user, True, False)])
    return [*ixs, fee]


def send_gasless(kora: Kora, ixs: list[Instruction], users: list[Keypair], programs: list[Pubkey], mint: Pubkey | None = None,
                 v1: bool = True) -> dict:
    """The whole round: read the node's policy, refuse early if it would refuse, build the v1 message with Kora's
    signer as fee payer, sign as the users, let Kora sign and send. Returns {signature, fee_payer}."""
    problems = policy_problems(kora.config(), programs, mint)
    if problems:
        raise KoraError("policy", "; ".join(problems))
    signer, _pay_to = kora.payer_signer()
    msg = message(ixs, signer, kora.blockhash(), v1=v1)
    return {"signature": kora.sign_and_send(user_signed(msg, users)), "fee_payer": str(signer)}
