"""The payout leg, in LiteSVM. LABEL: "LiteSVM (testkeys build), not devnet".

A knos_pay job pays only on a GitHub Actions OIDC token from a signed run of the prove.yml it pins (knos.settle.v2.pay:
`pay_ix` takes a verified token). That run exists only after the workflow is pushed and a pull request is merged on
GitHub, and this flow's work is judged locally, so no such token can exist for it. The payout is therefore replayed
here: the SAME job (repository id, issue, amount, terms bytes, workflow pin, mode) funded in LiteSVM with the
testkeys builds of knos_pay 2.2 and knos_oidc (tests/fixtures), and paid with a token the test build's seed key
signs, after the Knos referee's verdict passed. Nothing here is a devnet transaction; the flow says so on every line.

It needs a Knos checkout (tests/_pay2.py and tests/fixtures/*.so); from an installed wheel it answers why it cannot.
"""
from __future__ import annotations

import sys
from pathlib import Path

LABEL = "LiteSVM (testkeys build), not devnet"


def available(root: Path) -> str | None:
    """None when the LiteSVM payout can run from this checkout, else why not."""
    t = Path(root) / "tests"
    if not (t / "_pay2.py").is_file():
        return "no tests/_pay2.py: the LiteSVM payout needs a Knos checkout"
    for so in ("knos_pay_v2_test.so", "knos_oidc_v2_test.so"):
        if not (t / "fixtures" / so).is_file():
            return f"tests/fixtures/{so} is missing"
    try:
        import solders.litesvm  # noqa: F401
    except ImportError:
        return "solders.litesvm is not installed"
    return None


def pay_job(root: Path, *, repo_id: int, issue: int, amount: int, wf_repo: str, wf_sha: str, terms: bytes, head_sha: str,
            payee_wallet, payee_id: int, funder=None, mint=None, work_s: int = 86_400) -> dict:
    """Fund the job (from `funder`, the same wallet as on devnet when given) and pay it to `payee_wallet` in LiteSVM."""
    why = available(root)
    if why:
        return {"label": LABEL, "paid": False, "error": why}
    t = str(Path(root) / "tests")
    if t not in sys.path:
        sys.path.insert(0, t)
    from _pay2 import Chain  # noqa: PLC0415 - the test harness of a checkout

    from ..settle.v2 import pay
    c = Chain()
    sigs: list[str] = []
    send = c.svm.send_transaction
    c.svm.send_transaction = lambda tx: (sigs.append(str(tx.signatures[0])), send(tx))[1]
    m = c.new_mint(keypair=mint) if mint is not None else c.new_mint()
    fee_acct = c.token_account(pay.FEE_OWNER, m)
    who, tok = c.wallet(m, amount + 10_000_000, key=funder)
    if not c.send([pay.fund_wallet_ix(who.pubkey(), tok, m, repo_id, issue, amount, wf_repo, wf_sha, terms, pay.MERGE, work_s)], who, tag="fund_wallet"):
        return {"label": LABEL, "paid": False, "error": f"funding refused in LiteSVM: {c.err}"}
    fund_sig = sigs[-1]
    job = pay.job_pda(repo_id, issue, who.pubkey())
    j = pay.read_job(c.data(job))
    aud = pay.pay_audience(j.repo_id, j.issue, payee_id, head_sha, j.terms, j.mode, payee_wallet)
    tokacct = c.gh(aud, wf_repo=wf_repo, wf_sha=wf_sha, repository_id=j.repo_id)
    if tokacct is None:
        return {"label": LABEL, "paid": False, "error": f"the test token was not verified: {c.err}"}
    c.token_account(payee_wallet, m)
    ok = c.send([pay.pay_ix(c.payer.pubkey(), tokacct, c.key, job, j, payee_id, payee_wallet, used=c.data(tokacct))], tag="pay")
    return {"label": LABEL, "paid": bool(ok), "error": None if ok else c.err, "litesvm_fund_tx": fund_sig,
            "litesvm_pay_tx": sigs[-1] if ok else None, "job": str(job), "payee_wallet": str(payee_wallet),
            "to_payee_units": c.balance(pay.ata(payee_wallet, m)), "fee_units": c.balance(fee_acct), "mint": str(m),
            "why_litesvm": "knos_pay pays only on a GitHub Actions OIDC token from a signed run of the pinned prove.yml; "
                           "this flow's work was judged locally, so no such run exists (see PAIN: payout without GitHub Actions)"}
