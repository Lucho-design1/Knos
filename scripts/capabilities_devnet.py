"""The devnet runs behind docs/reference/DURABLE_NONCES.md, SAS_INPUTS.md, X402_UPTO.md and SPENDING_LIMITS.md.

    PYTHONPATH=src python scripts/capabilities_devnet.py KEYDIR [mint|nonce|sas|upto|squads ...] [--out FILE]

KEYDIR holds the operator's own devnet test wallets (payer.json pays, receiver.json is the payee/relay); every other
key is made fresh here and written to KEYDIR so a run can be continued. Devnet only, test tokens of a mint made here
(Token-2022, no extensions: "synthetic", no value). Nothing here signs with a Knos member key or touches Knos's
multisigs: the spending-limit run makes a multisig of its own fresh test keys. Prints one JSON line per step.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, create_account

from knos import chain
from knos.money import x402_upto as upto
from knos.platform import blockhash, nonce, sas, squads, token22
from knos.settle.v2 import pay

T22 = pay.TOKEN_2022
DECIMALS = 6


def key(dirp: Path, name: str) -> Keypair:
    p = dirp / f"{name}.json"
    if p.exists():
        return Keypair.from_bytes(bytes(json.loads(p.read_text())))
    k = Keypair()
    p.write_text(json.dumps(list(bytes(k))))
    p.chmod(0o600)
    return k


def say(**row) -> None:
    print(json.dumps(row), flush=True)
    OUT.append(row)


def mint_ixs(payer: Pubkey, mint: Pubkey, rent: int) -> list[Instruction]:
    """A Token-2022 mint with no extensions (82 bytes), InitializeMint2 (20), no freeze authority."""
    return [create_account(CreateAccountParams(from_pubkey=payer, to_pubkey=mint, lamports=rent, space=82, owner=T22)),
            Instruction(T22, bytes([20, DECIMALS]) + bytes(payer) + b"\x00", [AccountMeta(mint, False, True)])]


def mint_to_ix(mint: Pubkey, dest: Pubkey, authority: Pubkey, amount: int) -> Instruction:
    return Instruction(T22, bytes([7]) + amount.to_bytes(8, "little"), [AccountMeta(mint, False, True), AccountMeta(dest, False, True),
                                                                         AccountMeta(authority, True, False)])


def step_mint(L, d):
    payer, mint = key(d, "payer"), key(d, "mint")
    if L.account(mint.pubkey()) is None:
        sig = L.send(mint_ixs(payer.pubkey(), mint.pubkey(), L.rent(82)), payer, [mint], v1=True)
        say(step="mint", what="Token-2022 test mint, no extensions (synthetic)", mint=str(mint.pubkey()), signature=sig)
    owner, data = L.infos([mint.pubkey()])[0]
    verdict = token22.check(str(owner), data)
    say(step="mint-safety", mint=str(mint.pubkey()), token_2022=verdict["token_2022"], ok=verdict["ok"], said=verdict["said"])
    return mint.pubkey()


def step_nonce(L, d, mint: Pubkey):
    """A FundOrderWallet signed by the funder now, co-signed and sent by the relay after the blockhash window."""
    payer, relay, nk = key(d, "payer"), key(d, "receiver"), key(d, "nonce")
    tok = pay.ata(payer.pubkey(), mint, T22)
    L.send([pay.create_ata_ix(payer.pubkey(), payer.pubkey(), mint, T22), mint_to_ix(mint, tok, payer.pubkey(), 100 * 10 ** DECIMALS)], payer, v1=True)
    if nonce.read(L.account(nk.pubkey())) is None:
        sig = L.send(nonce.create_ixs(payer.pubkey(), nk.pubkey(), payer.pubkey(), L.rent(nonce.NONCE_SIZE)), payer, [nk], v1=True)
        say(step="nonce-account", nonce=str(nk.pubkey()), authority=str(payer.pubkey()), signature=sig)
    value = nonce.read(L.account(nk.pubkey())).value
    terms = pay.terms_json({"accept": "", "checks": [{"app": 15368, "name": "test"}], "mode": "merge", "v": 2, "synthetic": True})
    seq = int(time.time()) % 1_000_000
    fund = pay.fund_order_wallet_ix(payer.pubkey(), tok, mint, 1401439243, 286, 5 * 10 ** DECIMALS, "drexthealpha/knos-e2e", "0" * 40, terms,
                                    pay.MERGE, 3 * 86_400, seq, token_program=T22)
    msg = nonce.message([fund], relay.pubkey(), nk.pubkey(), payer.pubkey(), value, v1=True)
    part = nonce.sign_part(msg, [payer])                       # the funder signs on their machine, now
    signed_at = time.time()
    wait = max(blockhash.MEASURED_DEVNET_S * 1.5, 45.0)        # longer than any blockhash would live
    time.sleep(wait)
    full = nonce.add(nonce.decode(nonce.encode(part)), relay)  # the relay, later, elsewhere: adds its fee-payer signature
    sig = nonce.send(L, full)
    order = fund.accounts[1].pubkey
    o = pay.read_order(L.account(order))
    say(step="nonce-fund", order=str(order), signed_then_sent_after_s=round(time.time() - signed_at, 1), v1=True, uses_durable_nonce=full.uses_durable_nonce(),
        order_read_back=o is not None, signature=sig)
    # the same bytes can never land twice: the transaction advanced the nonce, so the value it signed over is gone
    # (sending them again only returns the same signature: a signature is a transaction's identity)
    say(step="nonce-replay", nonce_still_holds_signed_value=nonce.still_good(L, full), nonce_value_now=str(nonce.read(L.account(nk.pubkey())).value),
        signed_over=str(value))


def step_sas(L, d):
    issuer, lab = key(d, "payer"), key(d, "receiver")
    name, sname = "knos-test-lab-accreditor", "lab-accredited"
    cred = sas.credential_pda(issuer.pubkey(), name)
    layout, fields = bytes([12, 12, 10]), ["lab", "standard", "accredited"]
    schema = sas.schema_pda(cred, sname)
    ixs = []
    if L.account(cred) is None:
        ixs.append(sas.create_credential_ix(issuer.pubkey(), issuer.pubkey(), name, [issuer.pubkey()]))
    if L.account(schema) is None:
        ixs.append(sas.create_schema_ix(issuer.pubkey(), issuer.pubkey(), cred, sname, "A test issuer attests that a lab is accredited (synthetic)", layout, fields))
    if ixs:
        say(step="sas-issuer", credential=str(cred), schema=str(schema), signature=L.send(ixs, issuer, v1=True))
    att = sas.attestation_pda(cred, schema, lab.pubkey())
    if L.account(att) is None:
        data = sas.encode(layout, ["Synthetic Test Lab", "ISO/IEC 17025 (synthetic)", True])
        say(step="sas-attest", attestation=str(att),
            signature=L.send([sas.create_attestation_ix(issuer.pubkey(), issuer.pubkey(), cred, schema, lab.pubkey(), data, 0)], issuer, v1=True))
    good = sas.check(L, cred, schema, lab.pubkey(), expect={"accredited": True})
    other = sas.check(L, cred, schema, Keypair().pubkey())
    wrong = sas.check(L, cred, schema, lab.pubkey(), expect={"standard": "GLP"})
    say(step="sas-read", accepted=good.ok, why=good.why, fields=good.fields, unattested_subject=other.ok, unattested_why=other.why,
        wrong_value=wrong.ok, wrong_why=wrong.why)


def step_upto(L, d, mint: Pubkey):
    payer, payee, lab, auth = key(d, "payer"), key(d, "receiver"), key(d, "lab"), key(d, "authorizer")
    cluster = "devnet"
    splits = [(lab.pubkey(), 1_000)]                           # 10% of what is charged to the lab, the rest to the payee
    setup = [pay.create_ata_ix(payer.pubkey(), o, mint, T22) for o in (payer.pubkey(), payee.pubkey(), lab.pubkey(), upto.TREASURY_OWNER[cluster])]
    L.send(setup + [mint_to_ix(mint, pay.ata(payer.pubkey(), mint, T22), payer.pubkey(), 50 * 10 ** DECIMALS)], payer, v1=True)
    ceiling, used = 20 * 10 ** DECIMALS, 7 * 10 ** DECIMALS
    slot = int(chain.call(L.url, "getSlot", [{"commitment": "confirmed"}]))
    salt = int(time.time())
    req = upto.requirements(ceiling=ceiling, mint=mint, pay_to=payee.pubkey(), receiver_authorizer=auth.pubkey(), decimals=DECIMALS,
                            resource="https://knos.example/checks (synthetic)", splits=splits, token_program=T22)
    op = upto.open_ix(payer.pubkey(), payer.pubkey(), payee.pubkey(), mint, auth.pubkey(), salt, ceiling, req["extra"]["gracePeriodSeconds"],
                      slot, splits, T22)
    opened = upto.read_open(bytes(op.data), [a.pubkey for a in op.accounts])
    problems = upto.check_open(opened, req)
    sig_open = L.send([op], payer, v1=True)
    ch_addr = opened.channel
    ch = upto.read_channel(L.account(ch_addr))
    say(step="upto-open", channel=str(ch_addr), ceiling=ceiling, status=ch.status, server_check=problems or "matches the 402", signature=sig_open)
    before = {n: _bal(L, pay.ata(k, mint, T22)) for n, k in (("payer", payer.pubkey()), ("payee", payee.pubkey()), ("lab", lab.pubkey()))}
    ixs = upto.settle_ixs(auth, payee.pubkey(), ch, ch_addr, used, splits, cluster, T22)
    sig = L.send(ixs, payee, v1=True)                          # one v1 transaction: Ed25519 + settleAndSeal + distribute
    after = {n: _bal(L, pay.ata(k, mint, T22)) for n, k in (("payer", payer.pubkey()), ("payee", payee.pubkey()), ("lab", lab.pubkey()))}
    say(step="upto-settle", used=used, refunded_to_payer=after["payer"] - before["payer"], payee_got=after["payee"] - before["payee"],
        lab_got=after["lab"] - before["lab"], response=upto.response(sig, cluster, used, ceiling, payer.pubkey()), signature=sig)


def _bal(L, token_account: Pubkey) -> int:
    data = L.account(token_account)
    return int.from_bytes(data[64:72], "little") if data else 0


def step_squads(L, d, mint: Pubkey):
    payer, member2, ops, dest, ck = key(d, "payer"), key(d, "receiver"), key(d, "ops"), key(d, "lab"), key(d, "ms-create")
    ms_addr = squads.multisig_pda(ck.pubkey())
    if L.account(ms_addr) is None:
        cfg = L.account(squads.program_config_pda())
        treasury = Pubkey.from_bytes(cfg[48:80])
        sig = L.send([squads.multisig_create_v2_ix(ck.pubkey(), payer.pubkey(), treasury, [(payer.pubkey(), squads.ALL), (member2.pubkey(), squads.ALL)],
                                                   threshold=2)], payer, [ck], v1=True)
        say(step="squads-multisig", multisig=str(ms_addr), members=2, threshold=2, signature=sig, note="own fresh test keys, not Knos's")
    ms = squads.read_multisig(L.account(ms_addr))
    vault = squads.vault_pda(ms_addr)
    L.send([pay.create_ata_ix(payer.pubkey(), vault, mint, T22), mint_to_ix(mint, pay.ata(vault, mint, T22), payer.pubkey(), 50 * 10 ** DECIMALS),
            pay.create_ata_ix(payer.pubkey(), dest.pubkey(), mint, T22)], payer, v1=True)
    limit_key = key(d, f"limit-{ms.transaction_index + 1}")
    p = squads.plan(ms_addr, ms, limit_key.pubkey(), mint, 5 * 10 ** DECIMALS, "day", [ops.pubkey()], [dest.pubkey()], payer.pubkey())
    idx = p["transaction_index"]
    action = squads.add_spending_limit_action(limit_key.pubkey(), mint, 5 * 10 ** DECIMALS, "day", [ops.pubkey()], [dest.pubkey()])
    s1 = L.send([squads.config_transaction_create_ix(ms_addr, idx, payer.pubkey(), payer.pubkey(), [action], "knos: spending limit (test)"),
                 squads.proposal_create_ix(ms_addr, idx, payer.pubkey(), payer.pubkey()),
                 squads.proposal_approve_ix(ms_addr, idx, payer.pubkey())], payer, v1=True)
    s2 = L.send([squads.proposal_approve_ix(ms_addr, idx, member2.pubkey())], payer, [member2], v1=True)
    limit = squads.spending_limit_pda(ms_addr, limit_key.pubkey())
    s3 = L.send([squads.config_transaction_execute_ix(ms_addr, idx, payer.pubkey(), payer.pubkey(), [limit])], payer, v1=True)
    sl = squads.read_spending_limit(L.account(limit))
    say(step="squads-limit", spending_limit=str(limit), amount=sl.amount, period=sl.period, remaining=sl.remaining,
        members=[str(m) for m in sl.members], destinations=[str(x) for x in sl.destinations], create_and_approve=s1, second_vote=s2, execute=s3)
    use = squads.spending_limit_use_ix(ms_addr, ops.pubkey(), limit, dest.pubkey(), 3 * 10 ** DECIMALS, DECIMALS, mint, T22, memo="lab sample fee (synthetic)")
    s4 = L.send([use], payer, [ops], v1=True)
    left = squads.read_spending_limit(L.account(limit)).remaining
    try:
        L.simulate([squads.spending_limit_use_ix(ms_addr, ops.pubkey(), limit, dest.pubkey(), 3 * 10 ** DECIMALS, DECIMALS, mint, T22)], payer, [ops], v1=True)
        over = "not refused"
    except Exception as why:  # noqa: BLE001
        over = "refused: " + str(why)[:140]
    say(step="squads-use", spent=3 * 10 ** DECIMALS, remaining=left, second_use_over_limit=over, signature=s4)


OUT: list[dict] = []


def main(argv: list[str]) -> int:
    d = Path(argv[0]).expanduser()
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    steps = [a for a in argv[1:] if not a.startswith("--") and a != out] or ["mint", "sas", "upto", "squads", "nonce"]
    L = chain.ledger()
    mint = step_mint(L, d)
    for s in steps:
        if s == "mint":
            continue
        try:
            {"nonce": lambda: step_nonce(L, d, mint), "sas": lambda: step_sas(L, d), "upto": lambda: step_upto(L, d, mint),
             "squads": lambda: step_squads(L, d, mint)}[s]()
        except Exception as why:  # noqa: BLE001 - one step's failure is reported, the others still run
            say(step=s, failed=f"{type(why).__name__}: {str(why)[:400]}")
    if out:
        Path(out).write_text(json.dumps(OUT, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
