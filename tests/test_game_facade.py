"""knos.game's small contract: one attempt call for people and agents, a pool split by the referee's verdicts, the
Software Heritage content id, and a graduated result's record (Zenodo deposit labelled, fees from config/fees.yaml)."""
from __future__ import annotations

import hashlib

import pytest

from _game import TASK, FakeJudge, attempt as scored

import knos.game as game
from knos.autoresearch import task as artask
from knos.game.engine import Game
from knos.money import fees_config


def test_one_attempt_call_for_a_person_and_an_agent():
    for kind in ("human", "agent"):
        got = game.attempt("goal-1", "p1", kind, b"print(1)\n")
        assert got["goal"] == "goal-1" and got["player"] == "p1" and got["kind"] == kind
        assert got["artifact_hash"] == hashlib.sha256(b"print(1)\n").hexdigest()
    for bad in ("robot", "", None, "Human"):
        with pytest.raises(ValueError):
            game.attempt("goal-1", "p1", bad, b"x")


def test_an_attempt_on_a_game_is_judged_by_the_referee(tmp_path):
    g = Game.create(tmp_path / "g", TASK, title="facade", judge=FakeJudge(artask.load(TASK)))
    p = g.join("nemo", kind="agent")["player"]
    got = game.attempt(g, p, "agent", scored(g.baseline(), 0.8, 0.8).encode())
    assert got["goal"] == g.s["id"] and got["referee"]["decision"] == "scored"
    with pytest.raises(ValueError):
        game.attempt(g, p, "human", b"x")              # the player joined as an agent


def test_the_pool_goes_to_verified_attempts_in_proportion_to_each_players_best_score():
    atts = [{"player": "ada", "kind": "human", "verified": True, "score": 0.3},
            {"player": "ada", "kind": "human", "verified": True, "score": 0.1},
            {"player": "nemo", "kind": "agent", "verified": True, "score": 0.6},
            {"player": "eve", "kind": "agent", "verified": False, "score": 0.9},
            {"player": "zed", "kind": "human", "verified": True, "score": 0}]
    got = game.split_pool(1_000_000, atts)
    assert got == {"ada": 333_333, "nemo": 666_667} and sum(got.values()) == 1_000_000
    odd = game.split_pool(10, [{"player": n, "kind": "agent", "verified": True, "score": 1} for n in "abc"])
    assert sum(odd.values()) == 10 and sorted(odd.values()) == [3, 3, 4]
    assert game.split_pool(5_000_000, [{"player": "eve", "kind": "agent", "verified": False, "score": 0.9}]) == {}
    assert game.split_pool(5_000_000, []) == {}
    with pytest.raises(ValueError):
        game.split_pool(10, [{"player": "x", "kind": "robot", "verified": True, "score": 1}])
    with pytest.raises(ValueError):
        game.split_pool(-1, [])


def test_swhid_is_the_git_blob_hash():
    assert game.swhid(b"hello\n") == "swh:1:cnt:ce013625030ba8dba906f756967f9e9ca394464a"
    assert game.swhid(b"") == "swh:1:cnt:e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_a_graduated_records_zenodo_is_labelled_and_its_fees_come_from_the_config():
    r = game.graduation_record({"spec_hash": "ab" * 32, "passed": True, "swhid": game.swhid(b"x")}, amount=30_000_000)
    cfg = fees_config.load()
    assert r["zenodo"]["mode"] == "fixture" and r["zenodo"]["doi"] is None and "FIXTURE" in r["zenodo"]["label"]
    assert r["fees"]["graduation"] == cfg.fee("graduation", 30_000_000) and r["fees"]["payout"] == cfg.fee("payout", 30_000_000)
    live = game.graduation_record({"passed": True}, amount=1, zenodo={"mode": "live", "doi": "10.5072/zenodo.7"})
    assert live["zenodo"]["doi"] == "10.5072/zenodo.7"
