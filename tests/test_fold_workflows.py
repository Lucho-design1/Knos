"""The published workflows in the monorepo (docs/reference/MONOREPO.md): the same commits as drexthealpha/knos-workflows,
as the branch `workflows` of drexthealpha/Knos. An order pins sha256(<owner>/<name>) and the commit of the workflows
that may pay it, so the move is a new name in new orders, never a change to the program or to an order already funded.

In LiteSVM with the test issuer (tests/_order.py): a GitHub Actions token from a pushed run of the monorepo's branch
cannot exist before the founder pushes that branch, so the run's token is signed here by the test key, as every
LiteSVM test of knos_pay does. What it shows is the program's own rule on the two names."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD, NEW = "drexthealpha/knos-workflows", "drexthealpha/Knos"
PIN = "96b243f1b1dd5c975a0318dd9709a0da22b98dcd"      # the published commit the examples name (knos 0.3.28's workflows)


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- on chain: both homes pay the orders pinned to them, and neither pays the other's -------------------------------

@pytest.fixture(scope="module")
def chain():
    pytest.importorskip("solders.litesvm")
    from _order import OrderChain
    return OrderChain()


def _fund(c, wf_repo: str, wf_sha: str = PIN):
    from _order import REPO, TERMS, USDC, issue
    from knos.settle.v2 import pay
    ix = pay.fund_order_wallet_ix(c.funder.pubkey(), c.funder_tok, c.usdc, REPO, issue(), 20 * USDC, wf_repo, wf_sha, TERMS,
                                  token_program=c.token_program(c.usdc))
    assert c.send([ix], c.funder, tag="fund_order_wallet"), c.err
    return ix.accounts[1].pubkey


def _run(home: str, sha: str = PIN) -> dict:
    """The claims of prove.yml called from `home` at `sha`, as a caller pins it: `uses: <home>/.github/workflows/prove.yml@<sha>`."""
    return {"wf_repo": home, "wf_sha": sha, "job_workflow_ref": f"{home}/.github/workflows/prove.yml@{sha}"}


def test_an_order_pinned_to_the_monorepo_is_paid_by_its_run_and_by_no_other(chain):
    from solders.keypair import Keypair
    from _order import AUTHOR, USDC, code
    from knos.settle.v2 import pay
    c = chain
    order = _fund(c, NEW)
    o = c.order(order)
    assert bytes(o.wf_repo_hash) == pay.wf_repo_hash(NEW) != pay.wf_repo_hash(OLD) and o.wf_sha == PIN
    wallet = Keypair().pubkey()
    payees = [(AUTHOR, 10_000, wallet)]
    c.token_account(wallet, c.usdc)
    # the same commit in the old home is another workflow to this order: refused, E_WORKFLOW
    assert not c.pay(order, payees, **_run(OLD)) and code(c) == 86
    # the monorepo at another commit (its main, say, where prove.yml is the unlocked source) is refused too
    assert not c.pay(order, payees, **_run(NEW, "d" * 40)) and code(c) == 86
    # a repository merely called Knos under another owner is not the monorepo
    assert not c.pay(order, payees, **_run("someone/Knos")) and code(c) == 86
    assert c.pay(order, payees, **_run(NEW)), c.err
    assert c.balance(pay.ata(wallet, c.usdc)) == 20 * USDC and c.data(order) is None


def test_an_order_pinned_to_the_old_repository_keeps_being_paid_by_it_after_the_move(chain):
    from solders.keypair import Keypair
    from _order import AUTHOR, USDC, code
    from knos.settle.v2 import pay
    c = chain
    order = _fund(c, OLD)
    wallet = Keypair().pubkey()
    payees = [(AUTHOR, 10_000, wallet)]
    c.token_account(wallet, c.usdc)
    assert not c.pay(order, payees, **_run(NEW)) and code(c) == 86
    assert c.pay(order, payees, **_run(OLD)), c.err
    assert c.balance(pay.ata(wallet, c.usdc)) == 20 * USDC


def test_a_comment_in_a_repository_whose_caller_names_the_monorepo_funds_an_order_pinned_to_it(chain):
    """fund.yml's token carries job_workflow_ref; FundOrderBalance pins what it says. Nothing chooses the home but the caller."""
    from _order import issue
    from knos.settle.v2 import pay
    c = chain
    n = issue()
    tok = c.fund_token(n, wf_repo=NEW, wf_sha=PIN, job_workflow_ref=f"{NEW}/.github/workflows/fund.yml@{PIN}")
    ix = c.fund_balance_ix(tok, n)
    assert c.send([ix], tag="fund_order_balance"), c.err
    o = c.order(ix.accounts[7].pubkey)
    assert bytes(o.wf_repo_hash) == pay.wf_repo_hash(NEW) and o.wf_sha == PIN


# ---- off chain: the worker's words, the terms, the release script -----------------------------------------------------

def test_the_explainer_counts_both_homes_as_the_public_workflows():
    from knos import tasks
    assert tasks.PUBLIC_WORKFLOW_HOMES == (OLD, NEW) and tasks.PUBLIC_WORKFLOWS == NEW and tasks.OLD_PUBLIC_WORKFLOWS == OLD

    class Order:
        state, deadline, payee_id = "open", 2_000_000_000, 0

        def __init__(self, home):
            self.wf_repo_hash, self.wf_sha = tasks.repo_hash(home), PIN
    for home, public in ((OLD, True), (NEW, True), ("drexthealpha/knos-workflows-rc", False)):
        got = tasks.facts("octo/widgets#5", [Order(home)], 1_000)
        assert got["orders"][0]["wf_public"] is public, home


def test_terms_that_name_the_old_home_pay_only_its_runs_and_the_next_version_names_the_monorepo():
    from knos import terms3
    old = terms3.TEMPLATES["dataset-batch"]()
    new = terms3.moved(old)
    assert new["version"] == old["version"] + 1 and terms3.digest(new) != terms3.digest(old)
    assert all(s["workflow"].startswith(terms3.MONOREPO_WORKFLOWS) for s in new["evidence"]["sources"])
    for doc, good, bad in ((old, terms3.OLD_WORKFLOWS, terms3.MONOREPO_WORKFLOWS), (new, terms3.MONOREPO_WORKFLOWS, terms3.OLD_WORKFLOWS)):
        assert terms3.evaluator_allowed(doc, terms3.GITHUB, "acme/widgets", good + "prove.yml@" + PIN) == "own"
        assert terms3.evaluator_allowed(doc, terms3.GITHUB, "acme/widgets", bad + "prove.yml@" + PIN) is None
        assert terms3.evaluator_allowed(doc, terms3.GITHUB, "seller/knos-attest", good + "attest.yml@" + PIN, ("acme",)) == "neutral"
    assert terms3.moved(new) == new                         # nothing left to move: the same version


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in ["examples", ".github/workflows", "web/front.js", "web/install.js", "src/knos/settle/knos-claim.yml", "templates",
                "README.md", "LICENSE", "requirements", "programs-v2/program_ids.json"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if (ROOT / rel).is_dir() else shutil.copyfile)(ROOT / rel, root / rel)
    (root / "docs").mkdir()
    (root / "docs" / "VECTORS.json").write_text(f'"{NEW}/.github/workflows/prove.yml@refs/tags/v0.3.13"\n', encoding="utf-8")   # a claim, not a pin
    return root


def test_move_names_the_monorepo_everywhere_and_back_and_check_holds_one_home(tmp_path, monkeypatch, capsys):
    pub = _script("pinned_workflows")
    root = _tree(tmp_path)
    monkeypatch.setattr(pub, "ROOT", root)
    assert pub.home() == NEW and pub.main(["check"]) == 0                  # the tree names the monorepo since the 0.3.34 cutover
    assert pub.move(OLD) and pub.home() == OLD and pub.main(["check"]) == 0   # the tree as it was before the cutover
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    changed = pub.move(NEW)
    assert "examples/knos-workflow.yml" in changed and "web/front.js" in changed and "web/install.js" in changed
    assert any(c.startswith("templates/") for c in changed)
    assert pub.home() == NEW and pub.pin() == PIN
    capsys.readouterr()
    assert pub.main(["check"]) == 0 and f"every file names {NEW} at {PIN}" in capsys.readouterr().out
    text = (root / "examples" / "knos-workflow.yml").read_text(encoding="utf-8")
    assert f"uses: {NEW}/.github/workflows/prove.yml@{PIN}" in text and OLD + "/" not in text
    assert f"{NEW}/{PIN}/requirements/sign.txt" in (root / "examples" / "knos-canary.yml").read_text(encoding="utf-8")
    assert "refs/tags/v0.3.13" in (root / "docs" / "VECTORS.json").read_text(encoding="utf-8")
    # one file left in the old home is named, with the command that fixes it
    stale = root / "docs" / "STALE.md"
    stale.write_text(f"uses: {OLD}/.github/workflows/fund.yml@{PIN}\n", encoding="utf-8")
    assert pub.main(["check"]) == 1 and f"docs/STALE.md names the published workflows in {OLD}" in capsys.readouterr().out
    stale.unlink()
    assert pub.move(OLD) and pub.home() == OLD
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before          # back, byte for byte
    with pytest.raises(SystemExit):
        pub.move("drexthealpha/knos-workflows-rc")


def test_branch_prints_the_founders_commands_and_runs_none():
    pub = _script("pinned_workflows")
    lines = pub.branch_commands(PIN)
    assert lines[0] == f"git fetch https://github.com/{OLD}.git main" and f"git push origin workflows workflows-{PIN[:12]}" in lines
    assert any(line.startswith(f"git merge-base --is-ancestor {PIN} FETCH_HEAD") for line in lines)
    with pytest.raises(SystemExit):
        pub.branch_commands("main")
