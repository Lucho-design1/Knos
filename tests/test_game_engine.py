"""The Knos game's rules: one sealed goal, players through one door, the referee's static cheat rules, the Ladder on
the public board, rounds, refusals that put a cheater out, and verdicts on a second sealed set used once."""
from __future__ import annotations

import json
import sys

import pytest

from _game import TASK, FakeJudge, attempt

from knos.autoresearch import task as artask
from knos.game import ladder
from knos.game.engine import Game, GameError

SEALED_READ = "SEALED_HINT = open('referee/sealed.json').read()\n"


def _game(tmp_path, **rules):
    t = artask.load(TASK)
    return Game.create(tmp_path / "g", TASK, title="Synthetic rings", rules={"rounds": 2, "per_round": 3, **rules}, judge=FakeJudge(t))


def test_the_ladder_shows_only_gains_above_eta_rounded_down():
    assert ladder.rounded(0.8379, 0.01) == 0.83 and ladder.rounded(0.2, 0.01, maximize=False) == 0.2
    assert ladder.step(None, 0.8379) == (0.83, True)
    assert ladder.step(0.83, 0.835) == (0.83, False)          # a gain below eta is not shown
    assert ladder.step(0.83, 0.8451) == (0.84, True)
    assert ladder.step(0.83, 0.70) == (0.83, False)           # a worse attempt never lowers or reveals
    assert ladder.step(0.30, 0.25, maximize=False) == (0.25, True)
    with pytest.raises(ValueError):
        ladder.rounded(0.5, 0)


def test_players_join_with_a_key_and_the_same_door_for_people_and_agents(tmp_path):
    g = _game(tmp_path)
    a = g.join("ada", kind="human")
    b = g.join("nemo", kind="agent", label="MOCK Nemotron reply", github_id=7)
    assert a["player"] != b["player"] and len(a["key"]) > 20
    g.check_key(a["player"], a["key"])
    for bad in (None, "x", b["key"]):
        with pytest.raises(GameError):
            g.check_key(a["player"], bad)
    with pytest.raises(GameError):
        g.join("Ada")                                         # names are unique, case-blind
    with pytest.raises(GameError):
        g.join("eve", kind="robot")
    with pytest.raises(GameError):
        g.join("eve", payee="not-an-address")
    with pytest.raises(GameError):
        g.join("../etc")
    saved = json.loads((g.root / "game.json").read_text())
    assert a["key"] not in json.dumps(saved)                  # only the key's sha256 is kept
    assert [r["label"] for r in g.board() if r["name"] == "nemo"] == ["MOCK Nemotron reply"]


def test_an_honest_attempt_is_scored_a_cheat_is_refused_with_no_score_and_a_repeat_cheater_is_out(tmp_path):
    g = _game(tmp_path, per_round=5, max_refusals=2)
    p = g.join("ada")["player"]
    base = g.baseline()
    got = g.submit(p, {"train.py": attempt(base, 0.8379, 0.84)})
    assert (got["decision"], got["shown"], got["moved"]) == ("scored", 0.83, True)
    got = g.submit(p, {"train.py": attempt(base, 0.835, 0.84, "tiny")})
    assert (got["shown"], got["moved"]) == (0.83, False)
    cheat = g.submit(p, {"train.py": base.replace("CONFIG = {", SEALED_READ + "CONFIG = {", 1)})
    assert cheat["decision"] == "refused" and cheat["shown"] is None and "AR-SEALED" in cheat["rules"] and "data_tampering" in cheat["cheats"]
    other = g.submit(p, {"train.py": base + "\n# x", "conftest.py": "x = 1\n"})
    assert other["decision"] == "refused" and "AR-SCOPE" in other["rules"] and other["out"] is True
    with pytest.raises(GameError, match="out of the game"):
        g.submit(p, {"train.py": attempt(base, 0.99, 0.99)})


def test_the_baseline_again_and_a_crash_are_failures_not_cheats_and_sealed_output_is_withheld(tmp_path):
    g = _game(tmp_path, max_refusals=1)
    p = g.join("ada")["player"]
    same = g.submit(p, {"train.py": g.baseline()})
    assert same["decision"] == "failed" and same["cheats"] == [] and same["out"] is False
    crash = g.submit(p, {"train.py": g.baseline() + "\n# crash\n"})
    assert crash["decision"] == "failed" and "sealed row" not in json.dumps(crash)


def test_rounds_limit_attempts_and_the_game_closes(tmp_path):
    g = _game(tmp_path, per_round=2, rounds=2)
    p = g.join("ada")["player"]
    for k in range(2):
        g.submit(p, {"train.py": attempt(g.baseline(), 0.6 + k / 10, 0.6, str(k))})
    with pytest.raises(GameError, match="attempts a round"):
        g.submit(p, {"train.py": attempt(g.baseline(), 0.9, 0.9, "x")})
    assert g.close_round() == {"round": 2, "status": "open"}
    g.submit(p, {"train.py": attempt(g.baseline(), 0.9, 0.9, "y")})
    assert g.close_round()["status"] == "closed"
    with pytest.raises(GameError, match="not taking"):
        g.submit(p, {"train.py": attempt(g.baseline(), 0.9, 0.9, "z")})


def test_the_public_view_never_holds_a_hidden_score_or_another_players_file(tmp_path):
    g = _game(tmp_path)
    p = g.join("ada")["player"]
    g.submit(p, {"train.py": attempt(g.baseline(), 0.8379, 0.84, "secret-marker")})
    pub = json.dumps(g.public()) + json.dumps(g.board())
    assert "0.8379" not in pub and "secret-marker" not in pub and "key_sha256" not in pub
    assert g.public()["never_shown"] and "x0" in g.public_data("train").splitlines()[0]
    with pytest.raises(GameError):
        g.public_data("dev")


def test_finish_judges_each_players_best_on_the_final_set_once_and_ranks_by_lift(tmp_path):
    g = _game(tmp_path)
    base = g.baseline()
    a, b, c, d = (g.join(n)["player"] for n in ("ada", "bo", "cy", "di"))
    g.submit(a, {"train.py": attempt(base, 0.90, 0.52, "overfit dev")})     # best on dev, below the bar on final
    g.submit(a, {"train.py": attempt(base, 0.70, 0.70, "a2")})
    g.submit(b, {"train.py": attempt(base, 0.80, 0.80, "b")})
    g.submit(c, {"train.py": attempt(base, 0.75, 0.62, "c")})
    g.submit(d, {"train.py": base.replace("CONFIG = {", SEALED_READ + "CONFIG = {", 1)})
    f = g.finish()
    by = {v["name"]: v for v in f["verdicts"]}
    assert set(by) == {"ada", "bo", "cy"}                                     # a player with no scored attempt has no verdict
    assert by["ada"]["passed"] is False and "below the agreed" in by["ada"]["reasons"][0]   # its best-by-dev attempt is judged
    assert by["bo"]["passed"] and by["bo"]["rank"] == 1 and f["winner"] == b and by["cy"]["rank"] == 2
    assert by["bo"]["lift_per_seed"] == [0.3, 0.3] and f["judge_unchanged"] is True
    assert g.finish() is not None and g.s["status"] == "final"
    with pytest.raises(GameError):
        g.submit(b, {"train.py": attempt(base, 0.99, 0.99, "late")})
    with pytest.raises(GameError):
        g.pledge("late funder", 5_000_000)


def test_everything_is_in_knos_record_and_the_chain_verifies(tmp_path):
    g = _game(tmp_path)
    p = g.join("ada")["player"]
    g.submit(p, {"train.py": attempt(g.baseline(), 0.8, 0.8)})
    g.submit(p, {"train.py": g.baseline().replace("CONFIG = {", SEALED_READ + "CONFIG = {", 1)})
    g.pledge("funder one", 10_000_000, order="So11111111111111111111111111111111111111112", cluster="devnet")
    g.finish()
    kinds = [e["kind"] for e in g.rec.written]
    for k in ("claim", "paper", "experiment", "cheat", "refusal", "funding", "verdict"):
        assert k in kinds, k
    assert g.rec.verify()["ok"] is True


def test_reopening_a_game_keeps_its_state(tmp_path):
    g = _game(tmp_path)
    p = g.join("ada")
    g.submit(p["player"], {"train.py": attempt(g.baseline(), 0.8, 0.8)})
    again = Game.open(g.root, judge=FakeJudge(g.task))
    again.check_key(p["player"], p["key"])
    assert again.board()[0]["shown"] == 0.8 and again.history(p["player"])[0]["decision"] == "scored"
    with pytest.raises(GameError):
        Game.create(g.root, TASK, title="again")


def test_a_real_game_with_the_real_referee_three_players_and_a_refused_cheat(tmp_path):
    """The real LocalJudge (two seeded runs per attempt on the sealed synthetic data): MOCK Nemotron (which tries one
    cheat), the command protocol with the no-model local agent, and a synthetic scripted human."""
    from knos.game import players
    g = Game.create(tmp_path / "real", TASK, title="Synthetic rings, real referee", rules={"rounds": 1, "per_round": 2})
    a = g.join("nemotron", kind="agent", label="MOCK", github_id=1)["player"]
    b = g.join("local", kind="agent", label="local deterministic agent (no model)", github_id=2)["player"]
    h = g.join("ada", kind="human", label=players.SyntheticHuman.LABEL, github_id=3)["player"]
    nem, label = players.nemotron()
    assert "MOCK" in label or "Token Factory" in label
    loc, _ = players.command(f"{sys.executable} -m knos.game.local_agent")
    hum = players.SyntheticHuman()
    got = {pid: [players.play(g, pid, pr) for _ in range(2)] for pid, pr in ((a, nem), (b, loc), (h, hum))}
    assert [x["decision"] for x in got[a]] == ["scored", "refused"]            # the mock's second reply reads the sealed file
    assert all(x["decision"] == "scored" for x in got[b] + got[h])
    f = g.finish()
    assert f["winner"] in (a, b, h) and len(f["verdicts"]) == 3 and f["passed"][0] == f["winner"]
    assert f["baseline_final"] and all(0 <= s <= 1 for s in f["baseline_final"])
