"""v0.3.34 fix phase 2 (re-judges): the seal binds the hidden data's contents; a copy with a comment is still a copy;
only PROVEN players are paid (a wallet bound on chain), a fake "torvalds" is not; an honest win survives later
refusals; and the pot is funded and paid through the referee panel's verdict (knos_pay 0.3.34, LiteSVM here)."""
from __future__ import annotations

import re

import pytest

from _game import TASK
from test_game_fix34 import _csv_task

import knos.game as game
from knos.autoresearch import judge as arjudge
from knos.autoresearch import task as artask
from knos.autoresearch.judge import Verdict, judge_hash, static_findings
from knos.game import payout, pot
from knos.game.engine import Game, GameError, join_message
from knos.game.norm import normalized_sha256
from knos.settle.v2 import pay

W1, W2, W3 = ("So11111111111111111111111111111111111111112", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
              "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
TORVALDS = 1024025


class ProgramJudge:
    """Scores a file by the program it runs (a SCORE = (dev, final) assignment), never by its comments: the same program
    scores the same, as with the real referee. Static rules are the real ones."""

    backend = "tests.ProgramJudge"

    def __init__(self, task):
        self.task = task
        self.sealed_judge = judge_hash()

    def seal(self) -> dict:
        return {"spec_hash": self.task.spec_hash(self.sealed_judge), "judge_hash": self.sealed_judge, "editable": "train.py",
                "seeds": [1, 2], "tolerance": {"abs": 0.03}, "sealed_at": 0, "backend": self.backend}

    def judge(self, files, current, stage="dev"):
        found = static_findings(files, "train.py", current)
        if any(f.severity == "refuse" for f in found):
            return Verdict(False, reasons=["refused"], cheats=found)
        m = re.search(r"^SCORE = \(([0-9.]+), ([0-9.]+)\)", files["train.py"], re.M)
        dev, fin = (float(m.group(1)), float(m.group(2))) if m else (0.5, 0.5)
        s = dev if stage == "dev" else fin
        return Verdict(True, score=s, scores=[s, s], cheats=found)


def scored(base: str, dev: float, final: float) -> str:
    return base.replace("CONFIG = {", f"SCORE = ({dev}, {final})\n\nCONFIG = {{", 1)


def _game(tmp_path, root=TASK, **rules):
    return Game.create(tmp_path / "g", root, title="fix34b", rules={"per_round": 5, **rules}, judge=ProgramJudge(artask.load(root)))


# -- 1. the seal binds the hidden data ------------------------------------------------------------------------------
def test_swapping_hidden_labels_after_sealing_is_caught(tmp_path):
    root = _csv_task(tmp_path)
    g = _game(tmp_path, root)
    p = g.join("ada", github_id=1)["player"]
    g.submit(p, {"train.py": scored(g.baseline(), 0.8, 0.8)})
    final = root / "referee" / "hidden_final.csv"
    rows = final.read_text().splitlines()
    final.write_text("\n".join([rows[0]] + [",".join(r.split(",")[:-1] + ["1"]) for r in rows[1:]]) + "\n")
    with pytest.raises(GameError, match="sealed_changed"):
        g.submit(p, {"train.py": scored(g.baseline(), 0.9, 0.9)})
    f = g.finish()
    assert f["sealed_unchanged"] is False and f["winner"] is None
    assert all("sealed_changed" in " ".join(v["reasons"]) for v in f["verdicts"])
    # and a game opened again from disk (the judge's `knos game finish` in a new process) sees it too
    assert Game.open(g.root, judge=ProgramJudge(artask.load(root))).sealed_moved().startswith("sealed_changed")


def test_the_csv_spec_hash_and_the_autoresearch_graduation_bind_the_hidden_contents(tmp_path):
    root = _csv_task(tmp_path)
    t = artask.load(root)
    before = t.spec_hash("j" * 64)
    ref = arjudge.LocalJudge(t)
    (root / "referee" / "hidden_dev.csv").write_text((root / "referee" / "hidden_dev.csv").read_text().replace(",0\n", ",1\n", 3))
    assert artask.load(root).spec_hash("j" * 64) != before
    assert ref.sealed_changed().startswith("sealed_changed")
    f = ref.final(t.baseline, t.baseline)
    assert not f["graduated"] and any(r.startswith("sealed_changed") for r in f["reasons"])


# -- 2. a copy with a comment is a copy -----------------------------------------------------------------------------
def test_normalized_hash_ignores_comments_blank_lines_spacing_and_docstrings():
    a = 'def f(x):\n    """doc"""\n    return x + 1\n'
    assert normalized_sha256(a) == normalized_sha256("# hi\n\ndef f( x ):\n    return x+1   # same\n\n\n")
    assert normalized_sha256(a) != normalized_sha256("def f(x):\n    return x + 2\n")
    assert normalized_sha256("not python (\n# c\n a b") == normalized_sha256("not python(\na b")


def test_the_judges_winning_file_plus_a_comment_line_earns_nothing(tmp_path):
    g = _game(tmp_path)
    win = scored(g.baseline(), 0.9, 0.9)
    h1 = g.join("h1", github_id=11)["player"]
    others = [g.join(f"h{k}", github_id=10 + k)["player"] for k in (2, 3, 4)]
    g.submit(h1, {"train.py": win})
    for k, p in enumerate(others):
        g.submit(p, {"train.py": f"# copy {k}\n\n" + win.replace("CONFIG = {", "\n# tweak\nCONFIG = {", 1)})
    f = g.finish()
    by = {v["player"]: v for v in f["verdicts"]}
    assert by[h1]["passed"] and not any(by[p]["passed"] for p in others)
    assert [x["player"] for x in pot.split(f)["parts"]] == [h1]
    atts = [dict(game.attempt("g", n, "agent", (f"# {n}\n" + win).encode()), verified=True, score=0.4) for n in ("x", "y")]
    assert game.split_pool(10, atts) == {"x": 10}


# -- 3. only proven players are paid --------------------------------------------------------------------------------
class Chainless:
    """A ledger with some wallets bound on chain (knos_pay Bind accounts, 56 bytes)."""

    def __init__(self, binds: dict[int, str]):
        from solders.pubkey import Pubkey
        self.data = {}
        for uid, w in binds.items():
            self.data[str(pay.bind_pda(uid))] = bytes([1]) + bytes(7) + uid.to_bytes(8, "little") + bytes(Pubkey.from_string(w)) + (1).to_bytes(8, "little")

    def account(self, addr):
        return self.data.get(str(addr))


def _finished(tmp_path, players):
    g = _game(tmp_path)
    pids = {}
    for k, (name, kw) in enumerate(players):
        pids[name] = g.join(name, **kw)["player"]
        g.submit(pids[name], {"train.py": scored(g.baseline(), 0.9 - k / 100, 0.9 - k / 100)})
    g.finish()
    return g, pids


def test_a_fake_torvalds_is_ranked_but_never_paid(tmp_path):
    g, pids = _finished(tmp_path, [("torvalds", {"github_id": TORVALDS, "payee": W1}), ("ada", {"github_id": 2, "payee": W2})])
    assert g.s["final"]["winner"] == pids["torvalds"]                 # it plays and ranks
    led = Chainless({2: W2})
    who = payout.payees(led, g)
    assert who["proofs"][pids["torvalds"]]["proven"] is False and "claimed, not proven" in who["proofs"][pids["torvalds"]]["why"]
    assert who["payees"] == [(2, 10_000, W2)]
    # bound on chain, but to the real owner's wallet: an impostor naming its own payee is still not proven
    led2 = Chainless({TORVALDS: W3, 2: W2})
    assert payout.proven(led2, g, pids["torvalds"])["proven"] is False


def test_a_signature_by_the_bound_wallet_proves_the_id(tmp_path):
    from solders.keypair import Keypair
    g = _game(tmp_path)
    k = Keypair()
    sig = str(k.sign_message(join_message(g.s["id"], "drex")))
    pid = g.join("drex", github_id=77, pubkey=str(k.pubkey()), signature=sig)["player"]
    assert g.player(pid)["identity"] == "github:77" and g.player(pid)["proof_key"] == str(k.pubkey())
    g.submit(pid, {"train.py": scored(g.baseline(), 0.9, 0.9)})
    g.finish()
    led = Chainless({77: str(k.pubkey())})
    assert payout.proven(led, g, pid)["proven"] and payout.payees(led, g)["payees"] == [(77, 10_000, str(k.pubkey()))]
    assert payout.proven(Chainless({}), g, pid)["proven"] is False


# -- 4. forfeiture -------------------------------------------------------------------------------------------------
def test_refusals_after_an_honest_win_do_not_void_it(tmp_path):
    g = _game(tmp_path, max_refusals=2)
    p = g.join("alice", orcid="0000-0002-1825-0097")["player"]
    g.submit(p, {"train.py": scored(g.baseline(), 0.9, 0.9)})
    for _ in range(2):
        g.submit(p, {"train.py": g.baseline().replace("CONFIG = {", "X = open\nCONFIG = {", 1)})
    assert g.player(p)["out"] is True
    with pytest.raises(GameError, match="out of the game"):
        g.submit(p, {"train.py": scored(g.baseline(), 0.95, 0.95)})
    f = g.finish()
    assert f["winner"] == p and f["verdicts"][0]["passed"]


# -- 5. the pot through the referee panel's verdict (LiteSVM, knos_pay 0.3.34 test build) --------------------------
BUILD = "knos_pay_v2_0334_test.so"


def test_the_pot_is_funded_and_paid_to_proven_players_by_the_panel_verdict(tmp_path):
    pytest.importorskip("solders.litesvm")
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey

    from _order import USDC, OrderChain
    from _pay2 import ChainLedger
    from knos import chain
    c = OrderChain(pay_build=BUILD)
    led = ChainLedger(c)
    g = _game(tmp_path)
    referees = [Keypair() for _ in range(3)]
    payout.set_panel(g, 2, [str(r.pubkey()) for r in referees], str(pay.PAY_ID), str(c.usdc))
    walls = {n: Keypair().pubkey() for n in ("ada", "bo")}
    for gid, n in ((501, "ada"), (502, "bo")):
        assert c.bind(gid, walls[n]), c.err                             # proven: bound on chain by the claim workflow
    ada = g.join("ada", github_id=501, payee=str(walls["ada"]))["player"]
    bo = g.join("bo", github_id=502)["player"]
    fake = g.join("torvalds", github_id=TORVALDS, payee=str(Keypair().pubkey()))["player"]
    for k, p in enumerate((fake, ada, bo)):
        g.submit(p, {"train.py": scored(g.baseline(), 0.95 - k / 20, 0.95 - k / 20)})
    funders = [c.wallet(c.usdc, 100 * USDC) for _ in range(2)]
    for (f, tok), amt in zip(funders, (20 * USDC, 10 * USDC)):
        assert c.send([payout.fund_ix(g, f.pubkey(), tok, amt)], f), c.err
        g.pledge(f"funder {str(f.pubkey())[:6]}", amt, order=str(payout.order_address(g, f.pubkey())))
    seen = payout.pot_on_chain(led, g)
    assert seen["locked"] == 30 * USDC and seen["funders"] == 2
    g.finish()
    who = payout.payees(led, g)
    rows = who["payees"]
    assert [r[0] for r in rows] == [501, 502] and sum(r[1] for r in rows) == 10_000      # torvalds ranked first, not paid
    for w in walls.values():
        c.token_account(w, c.usdc)
    for r in seen["orders"]:
        order = Pubkey.from_string(r["order"])
        for ref in referees[:2]:
            o = c.order(order)
            ixs = payout.verdict_ixs(c.payer.pubkey(), g, order, o, rows, [payout.sign(ref, g, order, o, rows)])
            assert chain.tx_size(ixs, c.payer.pubkey(), v1=True) <= chain.MAX_V1_BYTES
            assert c.send(ixs, mark=False), c.err
        assert c.order(order) is None
    from knos.money import fees_config
    want = [a + b for a, b in zip(fees_config.amounts(20 * USDC, [r[1] for r in rows]), fees_config.amounts(10 * USDC, [r[1] for r in rows]))]
    got = [int.from_bytes(c.data(pay.ata(walls[n], c.usdc))[64:72], "little") for n in ("ada", "bo")]
    assert got == want and sum(got) == 30 * USDC


def test_with_no_proven_passer_the_panel_refunds_the_pot(tmp_path):
    pytest.importorskip("solders.litesvm")
    from solders.keypair import Keypair

    from _order import USDC, OrderChain
    from _pay2 import ChainLedger
    c = OrderChain(pay_build=BUILD)
    g = _game(tmp_path)
    referees = [Keypair() for _ in range(3)]
    payout.set_panel(g, 2, [str(r.pubkey()) for r in referees], str(pay.PAY_ID), str(c.usdc))
    p = g.join("torvalds", github_id=TORVALDS)["player"]
    g.submit(p, {"train.py": scored(g.baseline(), 0.9, 0.9)})
    f, tok = c.wallet(c.usdc, 100 * USDC)
    assert c.send([payout.fund_ix(g, f.pubkey(), tok, 10 * USDC)], f), c.err
    order = payout.order_address(g, f.pubkey())
    g.finish()
    rows = payout.payees(ChainLedger(c), g)["payees"]
    assert rows == []
    before = int.from_bytes(c.data(tok)[64:72], "little")
    o = c.order(order)
    for ref in referees[1:]:
        o = c.order(order)
        assert c.send(payout.verdict_ixs(c.payer.pubkey(), g, order, o, rows, [payout.sign(ref, g, order, o, rows)]), mark=False), c.err
    assert c.order(order) is None and int.from_bytes(c.data(tok)[64:72], "little") - before == 10 * USDC + o.fee


def test_the_panel_is_fixed_once_a_pledge_exists(tmp_path):
    from solders.keypair import Keypair
    g = _game(tmp_path)
    keys = [str(Keypair().pubkey()) for _ in range(3)]
    payout.set_panel(g, 2, keys, str(pay.PAY_ID), W1)
    g.pledge("someone", 5_000_000, order=W2)
    with pytest.raises(payout.PayoutError, match="fixed"):
        payout.set_panel(g, 1, keys[:1], str(pay.PAY_ID), W1)
    with pytest.raises(payout.PayoutError):
        payout.set_panel(_game(tmp_path / "b"), 3, keys[:2], str(pay.PAY_ID), W1)


def test_a_long_openalex_field_name_is_accepted(tmp_path):
    g = Game.create(tmp_path / "f", TASK, title="field", field="Biochemistry, Genetics and Molecular Biology",
                    judge=ProgramJudge(artask.load(TASK)))
    assert g.s["field"] == "Biochemistry, Genetics and Molecular Biology"
