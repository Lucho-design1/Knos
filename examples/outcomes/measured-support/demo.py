"""The measured-outcome demo on devnet, step by step, with SYNTHETIC support tickets.

    python examples/outcomes/measured-support/demo.py prepare --keys DIR --repo OWNER/NAME --work DIR
    python examples/outcomes/measured-support/demo.py fund    --keys DIR --work DIR
    python examples/outcomes/measured-support/demo.py data    --work DIR        after the window has closed
    python examples/outcomes/measured-support/demo.py run     --work DIR        starts prove.yml, waits, downloads the artifacts
    python examples/outcomes/measured-support/demo.py relay   --keys DIR --work DIR   verifies each tier's token, pays the tier
    python examples/outcomes/measured-support/demo.py refund  --keys DIR --work DIR   after the deadline: the tiers not signed for
    python examples/outcomes/measured-support/demo.py status  --keys DIR --work DIR   reads the chain, writes demo.json

DIR (--keys) holds buyer.json (the funding wallet, which also pays the fees and relays), seller.json (whose address
the tiers pay) and mint.txt (a test SPL mint of 6 decimals the buyer holds; it stands in for USDC and is worth
nothing). --repo is a repository of the runner's own GitHub account (the demo used a new private one) to which this
pushes outcome.yaml, the lock, prove.yml, knos-outcome.yml and a copy of the measuring code. State is kept in
<work>/demo-state.json, so each step runs once and the demo can be resumed. Devnet only; no key is printed.

The tickets are made up (knos.outcomes.synth): the "AI agent" and its lift are chosen parameters, and the numbers say
nothing about any real agent, help desk or customer.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from solders.pubkey import Pubkey  # noqa: E402

from knos import chain  # noqa: E402
from knos.outcomes import escrow, measure, recordio, sign, synth, yamlish  # noqa: E402
from knos.outcomes.spec import spec_hash, utc  # noqa: E402
from knos.settle.v2 import oidc, pay  # noqa: E402

RPC = os.environ.get("KNOS_RPC", "https://api.devnet.solana.com")
LEAD, WINDOW, AFTER = 6 * 60, 10 * 60, 30 * 60       # the window opens 6 min after prepare, lasts 10; the orders' deadline is 30 min after the window
N_WINDOW, N_HISTORY = 10_000, 300
SELLER_GH = ("drexthealpha", 142920951)              # the runner's own account stands for both parties (one person ran the demo)
DATA_BRANCH = "outcome-data"


def sh(*args: str, cwd: Path | None = None, check: bool = True, capture: bool = True) -> str:
    done = subprocess.run(list(args), cwd=cwd, capture_output=capture, text=True, check=False)  # noqa: S603
    if check and done.returncode:
        raise SystemExit(f"{' '.join(args[:3])} failed: {(done.stderr or done.stdout or '').strip()[-400:]}")
    return (done.stdout or "").strip()


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(work: Path) -> dict:
    p = work / "demo-state.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def save_state(work: Path, st: dict) -> None:
    (work / "demo-state.json").write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")


def keys(d: Path):
    return chain.wallet(d / "buyer.json"), chain.wallet(d / "seller.json"), Pubkey.from_string((d / "mint.txt").read_text().strip())


def say(text: str) -> None:
    print(text, flush=True)


# ---- prepare: the spec, the lock, the signatures, the repository --------------------------------------------------------
def prepare(a) -> None:
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    st = load_state(work)
    if st.get("pinned"):
        say(f"prepared already: {a.repo} at {st['pinned']}")
        return
    buyer, seller, mint = keys(Path(a.keys))
    repo = a.repo
    if sh("gh", "repo", "view", repo, "--json", "id", check=False) == "":
        sh("gh", "repo", "create", repo, "--private", "--description", "Knos outcome demo: SYNTHETIC support tickets, devnet only")
    repo_id = int(sh("gh", "api", f"repos/{repo}", "--jq", ".id"))
    issues = json.loads(sh("gh", "api", f"repos/{repo}/issues?state=all", "--jq", "[.[] | .number]") or "[]")
    issue = issues[-1] if issues else int(sh("gh", "api", f"repos/{repo}/issues", "-f", "title=Measured outcome: AI agent resolves support tickets (SYNTHETIC)",
                                             "-f", "body=The orders of the Knos outcome demo. SYNTHETIC data, devnet test token.", "--jq", ".number"))
    t0 = int(time.time()) + LEAD
    s = synth.example_spec(start=iso(t0), end=iso(t0 + WINDOW), salt=secrets.token_hex(16), funder=str(buyer.pubkey()), seller=str(seller.pubkey()),
                           mint=str(mint), repository=repo, repository_id=repo_id, issue=issue, seq_start=int(time.time()) % 100_000,
                           work_seconds=LEAD + WINDOW + AFTER)
    s["data"]["ref"] = DATA_BRANCH
    s["dispute_window_days"] = 0          # a demo of minutes: the orders' deadline is 30 minutes after the window (AFTER)
    s["parties"]["seller"].update(github=SELLER_GH[0], id=SELLER_GH[1])
    history = synth.tickets(s, 0, seed=11, before=N_HISTORY)
    lock = measure.lock_for(s, history, escrow.orders(s))
    sigs = {"spec_hash": spec_hash(s), "signatures": [sign.sign(s, "buyer", buyer), sign.sign(s, "seller", seller)]}
    assert sign.verify(s, sigs) == []
    tree = work / "repo"
    if tree.exists():
        shutil.rmtree(tree)
    (tree / ".github" / "workflows").mkdir(parents=True)
    (tree / "outcome.yaml").write_text(yamlish.dumps(s, {"title": "SYNTHETIC data: made-up support tickets for the Knos outcome demo. Devnet, a test token.",
                                                         "control": "A public salt, fixed before the window opened."}), encoding="utf-8")
    (tree / "outcome.lock.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    (tree / "outcome.signatures.json").write_text(json.dumps(sigs, indent=2, sort_keys=True) + "\n")
    shutil.copy(HERE / "prove.yml.in", tree / ".github" / "workflows" / "prove.yml")
    shutil.copy(ROOT / ".github" / "workflows" / "knos-outcome.yml", tree / ".github" / "workflows" / "knos-outcome.yml")
    vend = tree / ".knos" / "vendor" / "knos" / "outcomes"
    vend.mkdir(parents=True)
    (vend.parent / "__init__.py").write_text('"""The measuring code of Knos Outcomes, copied for the demo (knos.outcomes)."""\n')
    for f in sorted((ROOT / "src" / "knos" / "outcomes").iterdir()):
        if f.suffix in (".py", ".json"):
            shutil.copy(f, vend / f.name)
    (tree / "README.md").write_text("# Knos outcome demo (SYNTHETIC)\n\nMade-up support tickets, measured by `.github/workflows/prove.yml` against "
                                    "`outcome.yaml`; three tiers of a devnet test token. Nothing here is a real customer, agent or help desk.\n")
    sh("git", "init", "-q", "-b", "main", cwd=tree)          # commits under the runner's own git identity
    sh("git", "add", "-A", cwd=tree)
    sh("git", "commit", "-q", "-m", "Outcome spec, lock and measuring workflow (SYNTHETIC demo)", cwd=tree)
    url = f"https://github.com/{repo}.git"
    sh("git", "push", "-q", "-f", url, "main", cwd=tree)
    pinned = sh("git", "rev-parse", "HEAD", cwd=tree)
    # the data branch: the history only, before the window opens
    sh("git", "checkout", "-q", "--orphan", DATA_BRANCH, cwd=tree)
    sh("git", "rm", "-q", "-rf", ".", cwd=tree)
    (tree / "tickets.csv").write_text(synth.to_csv(history))
    sh("git", "add", "tickets.csv", cwd=tree)
    sh("git", "commit", "-q", "-m", "SYNTHETIC tickets before the window", cwd=tree)
    sh("git", "push", "-q", "-f", url, DATA_BRANCH, cwd=tree)
    sh("git", "checkout", "-q", "main", cwd=tree)
    comment = sign.comment(s, sigs, escrow.orders(s))
    sh("gh", "api", f"repos/{repo}/issues/{issue}/comments", "-f", f"body={comment}", "--jq", ".id")
    st.update(repo=repo, repo_id=repo_id, issue=issue, pinned=pinned, spec=s, spec_hash=spec_hash(s), orders=escrow.orders(s),
              window=s["window"], prepared_at=int(time.time()))
    save_state(work, st)
    say(f"pinned {repo}@{pinned}; spec {spec_hash(s)}; window {s['window']['start']} .. {s['window']['end']}")


# ---- fund: one order per tier ------------------------------------------------------------------------------------------
def fund(a) -> None:
    work = Path(a.work)
    st = load_state(work)
    if st.get("funded"):
        say("funded already")
        return
    buyer, _seller, mint = keys(Path(a.keys))
    s = st["spec"]
    if int(time.time()) >= utc(s["window"]["start"]):
        raise SystemExit("the window has opened: fund before it opens (prepare again for a new window)")
    led = chain.Ledger(RPC)
    tok = pay.ata(buyer.pubkey(), mint)
    sigs = []
    for k, ix in enumerate(escrow.fund_ixs(s, st["pinned"], buyer.pubkey(), tok, mint, now=led.now())):
        sig = led.send([ix], buyer)
        sigs.append(sig)
        recordio.money("funding", spec_hash=st["spec_hash"], tier=s["tiers"][k]["name"], amount=st["orders"][k]["amount"], mint=str(mint), tx=sig,
                       synthetic=True, root=work / "record")
        say(f"funded tier {s['tiers'][k]['name']}: {sig}")
    for owner in (buyer.pubkey(), pay.FEE_OWNER):           # the relayer's tip account and the fee owner's, for PayOrder
        if led.account(pay.ata(owner, mint)) is None:
            say(f"token account for {owner}: {led.send([pay.create_ata_ix(buyer.pubkey(), owner, mint)], buyer)}")
    for o in st["orders"]:
        got = pay.read_order(led.account(Pubkey.from_string(o["address"])))
        assert got is not None and got.amount == o["amount"] and got.wf_sha == st["pinned"] and got.terms.hex() == o["terms_hash"]
    st.update(funded=sigs, funded_at=int(time.time()), deadline=pay.read_order(led.account(Pubkey.from_string(st["orders"][0]["address"]))).deadline)
    save_state(work, st)


# ---- data: the window's tickets, pushed after it closed -------------------------------------------------------------------
def data(a) -> None:
    work = Path(a.work)
    st = load_state(work)
    s = st["spec"]
    left = utc(s["window"]["end"]) - int(time.time())
    if left > 0:
        raise SystemExit(f"the window closes in {left} s")
    if st.get("data_commit"):
        say(f"pushed already: {st['data_commit']}")
        return
    tree = work / "repo"
    history = synth.tickets(s, 0, seed=11, before=N_HISTORY)
    window = synth.tickets(s, N_WINDOW, seed=12, p_control=0.45, p_treated=0.53)
    sh("git", "checkout", "-q", DATA_BRANCH, cwd=tree)
    (tree / "tickets.csv").write_text(synth.to_csv(history + window))
    sh("git", "add", "tickets.csv", cwd=tree)
    sh("git", "commit", "-q", "-m", "SYNTHETIC tickets of the window", cwd=tree)
    sh("git", "push", "-q", f"https://github.com/{st['repo']}.git", DATA_BRANCH, cwd=tree)
    st["data_commit"] = sh("git", "rev-parse", "HEAD", cwd=tree)
    sh("git", "checkout", "-q", "main", cwd=tree)
    save_state(work, st)
    say(f"data {st['data_commit']}")


# ---- run: prove.yml at the pinned commit -----------------------------------------------------------------------------------
def run(a) -> None:
    work = Path(a.work)
    st = load_state(work)
    repo = st["repo"]
    if not st.get("run_id"):
        before = sh("gh", "run", "list", "-R", repo, "--workflow", "prove.yml", "--limit", "1", "--json", "databaseId", "--jq", ".[0].databaseId // 0")
        sh("gh", "workflow", "run", "prove.yml", "-R", repo, "--ref", "main")
        for _ in range(30):
            time.sleep(4)
            now = sh("gh", "run", "list", "-R", repo, "--workflow", "prove.yml", "--limit", "1", "--json", "databaseId", "--jq", ".[0].databaseId // 0")
            if now and now != before:
                st["run_id"] = int(now)
                save_state(work, st)
                break
    rid = st["run_id"]
    sh("gh", "run", "watch", str(rid), "-R", repo, "--interval", "10", check=False, capture=False)
    info = json.loads(sh("gh", "run", "view", str(rid), "-R", repo, "--json", "conclusion,headSha,jobs"))
    st["run"] = {"id": rid, "conclusion": info["conclusion"], "head": info["headSha"], "jobs": {j["name"]: j["conclusion"] for j in info["jobs"]},
                 "url": f"https://github.com/{repo}/actions/runs/{rid}"}
    out = work / "artifacts"
    if out.exists():
        shutil.rmtree(out)
    sh("gh", "run", "download", str(rid), "-R", repo, "--dir", str(out), check=False)
    save_state(work, st)
    say(json.dumps(st["run"], indent=2))


# ---- relay: each signed tier is verified by knos_oidc and paid by knos_pay -----------------------------------------------------
def relay_(a) -> None:
    from knos.settle.v2 import relay
    work = Path(a.work)
    st = load_state(work)
    buyer, seller, mint = keys(Path(a.keys))
    led = chain.Ledger(RPC)
    signed = work / "artifacts" / "knos-outcome-signed"
    jwks = None                                             # the relay reads GitHub's key set itself
    paid = st.setdefault("paid", {})
    for jf in sorted(signed.glob("tier-*.jwt")):
        aud = (signed / jf.name.replace(".jwt", ".aud")).read_text().strip()
        order = Pubkey.from_string(aud.split(":")[2])
        if str(order) in paid:
            continue
        o = pay.read_order(led.account(order))
        if o is None:
            say(f"{order} is closed already")
            continue
        jwt = jf.read_text().strip()
        seen = relay.verify_only(led, buyer, jwt, jwks)
        if not seen.get("ok"):
            raise SystemExit(f"knos_oidc did not verify {jf.name}: {seen.get('why')}")
        account = Pubkey.from_string(seen["account"])
        t = oidc.read_token(led.account(account))
        before = int(led.accounts([pay.ata(seller.pubkey(), mint)])[0] is not None)
        sig = led.send([pay.pay_order_ix(buyer.pubkey(), account, t.key, order, o, [(SELLER_GH[1], seller.pubkey())], pr=o.issue, used=jwt)], buyer)
        k = next(x["tier"] for x in st["orders"] if x["address"] == str(order))
        paid[str(order)] = {"tier": st["orders"][k]["name"], "verify": seen.get("sigs", []), "pay": sig, "amount": o.amount, "token_account": str(account),
                            "created_dest": not before}
        recordio.money("payout", spec_hash=st["spec_hash"], tier=st["orders"][k]["name"], amount=o.amount, mint=str(mint), tx=sig, synthetic=True,
                       root=work / "record")
        save_state(work, st)
        say(f"paid tier {st['orders'][k]['name']}: {sig}")


# ---- refund: after the deadline, the tiers not signed for -----------------------------------------------------------------------
def refund(a) -> None:
    work = Path(a.work)
    st = load_state(work)
    buyer, _seller, mint = keys(Path(a.keys))
    led = chain.Ledger(RPC)
    done = st.setdefault("refunded", {})
    for o_ in st["orders"]:
        addr = Pubkey.from_string(o_["address"])
        o = pay.read_order(led.account(addr))
        if o is None or o_["address"] in done:
            continue
        if led.now() <= o.pay_until:
            raise SystemExit(f"tier {o_['name']}: its deadline is {iso(o.pay_until)} (chain time now {iso(led.now())})")
        sig = led.send([pay.refund_order_ix(buyer.pubkey(), addr, o)], buyer)
        done[o_["address"]] = {"tier": o_["name"], "refund": sig, "amount": o.amount + o.fee}
        recordio.money("refund", spec_hash=st["spec_hash"], tier=o_["name"], amount=o.amount + o.fee, mint=str(mint), tx=sig, synthetic=True,
                       root=work / "record")
        save_state(work, st)
        say(f"refunded tier {o_['name']}: {sig}")


# ---- status: what the chain says, written beside this script ---------------------------------------------------------------------
def status(a) -> None:
    work = Path(a.work)
    st = load_state(work)
    _buyer, seller, mint = keys(Path(a.keys))
    led = chain.Ledger(RPC)
    result = None
    rp = work / "artifacts" / "knos-outcome-result" / "result.json"
    if rp.is_file():
        result = json.loads(rp.read_text())
    tiers = []
    for o_ in st["orders"]:
        addr = o_["address"]
        live = pay.read_order(led.account(Pubkey.from_string(addr)))
        state = "open" if live else ("paid" if addr in st.get("paid", {}) else "refunded" if addr in st.get("refunded", {}) else "closed")
        row = {"tier": o_["name"], "order": addr, "amount": o_["amount"], "fee": o_["fee"], "terms_hash": o_["terms_hash"], "state": state,
               "fund_tx": st["funded"][o_["tier"]]}
        if addr in st.get("paid", {}):
            row.update(pay_tx=st["paid"][addr]["pay"], verify_txs=st["paid"][addr]["verify"])
        if addr in st.get("refunded", {}):
            row.update(refund_tx=st["refunded"][addr]["refund"])
        if live is None and state == "closed":
            # closed by somebody else: the public relay refunds every order past its deadline (no token is needed)
            for sig, _slot in led.recent(Pubkey.from_string(addr), 10):
                said = " ".join(led.logs(sig))
                if f"knos3:refunded order={addr}" in said:
                    row.update(state="refunded", refund_tx=sig, refunded_by=led.payer_of(sig))
                    st.setdefault("refunded", {})[addr] = {"tier": o_["name"], "refund": sig, "amount": o_["amount"] + o_["fee"], "by": row["refunded_by"]}
                    recordio.money("refund", spec_hash=st["spec_hash"], tier=o_["name"], amount=o_["amount"] + o_["fee"], mint=str(mint), tx=sig,
                                   synthetic=True, root=work / "record")
                    save_state(work, st)
                elif f"knos3:paid order={addr}" in said:
                    row.update(state="paid", pay_tx=sig, paid_by=led.payer_of(sig))
        if result:
            t = result["tiers"][o_["tier"]]
            row.update(min_lift=t["min_lift"], measured_pass=t["passed"])
        tiers.append(row)
    seller_tokens = led.accounts([pay.ata(seller.pubkey(), mint)])[0]
    doc = {"synthetic": True, "what": "SYNTHETIC support tickets; a devnet test token minted for this demo stands in for USDC and is worth nothing",
           "cluster": "devnet", "program": str(pay.PAY_ID), "verifier": str(oidc.OIDC_ID), "repository": st["repo"], "repository_id": st["repo_id"],
           "issue": st["issue"], "pinned_commit": st["pinned"], "spec_hash": st["spec_hash"], "window": st["window"], "mint": str(mint),
           "data_commit": st.get("data_commit"), "run": st.get("run"), "tiers": tiers,
           "seller_balance": int.from_bytes(seller_tokens[64:72], "little") if seller_tokens else 0,
           "measurement": {k: result[k] for k in ("lift", "lower_bound", "confidence", "treated", "control", "bootstrap", "result_hash", "passed", "refused")}
           if result else None, "read_at": iso(led.now())}
    (HERE / a.out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    say(json.dumps(doc, indent=2, sort_keys=True))


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["prepare", "fund", "data", "run", "relay", "refund", "status"])
    p.add_argument("--keys", required=True, help="the folder with buyer.json, seller.json and mint.txt")
    p.add_argument("--repo", default="drexthealpha/knos-v0329-outcomes")
    p.add_argument("--work", required=True, help="a folder for the demo's state, the repository and the artifacts")
    p.add_argument("--out", default="demo.json", help="status: the file written beside this script")
    a = p.parse_args(argv)
    if "mainnet" in RPC:
        raise SystemExit("devnet only")
    {"prepare": prepare, "fund": fund, "data": data, "run": run, "relay": relay_, "refund": refund, "status": status}[a.step](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
