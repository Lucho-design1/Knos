"""The game's players: Nemotron (MOCK without NEBIUS_API_KEY, labelled), the Claude Agent SDK adapter (needs
ANTHROPIC_API_KEY; tested with a scripted query, never a model), the command protocol and a synthetic scripted human."""
from __future__ import annotations

import pytest

from _game import TASK, FakeJudge

from knos.autoresearch import proposers
from knos.autoresearch import task as artask
from knos.game import local_agent, players
from knos.game.engine import Game


def _ctx(best=None):
    t = artask.load(TASK)
    return proposers.Context(t.program, t.idea, t.editable, best or t.baseline, [])


class _Text:
    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, blocks, cost=None):
        self.content = blocks
        self.total_cost_usd = cost
        self.result = None


def test_the_claude_agent_player_needs_its_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(players.PlayerUnavailable, match="ANTHROPIC_API_KEY"):
        players.claude_agent()


def test_the_claude_agent_adapter_turns_a_reply_into_one_candidate_file():
    seen = {}
    ctx = _ctx()
    new = proposers.write_config(ctx.best, {**proposers.read_config(ctx.best), "standardize": True})

    async def fake_query(*, prompt, options=None):
        seen["prompt"], seen["options"] = prompt, options
        yield _Msg([_Text("Here it is.\n```python\n# change: standardize\n" + new + "```")])
        yield _Msg([], cost=0.0123)

    p, label = players.claude_agent(query_fn=fake_query)
    assert "not a model" in label
    cand = p.propose(ctx)
    assert cand.files == {"train.py": "# change: standardize\n" + new} and cand.change == "standardize"
    assert "never shown" in seen["prompt"] and p.cost_usd == 0.0123

    async def says_nothing(*, prompt, options=None):
        yield _Msg([_Text("no code")])
    assert players.claude_agent(query_fn=says_nothing)[0].propose(ctx) is None


def test_nemotron_without_a_key_is_labelled_mock(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    p, label = players.nemotron(cheat_at=())
    assert label.startswith("MOCK")
    c = p.propose(_ctx())
    assert c is not None and c.files["train.py"] != _ctx().best and p.client.calls[-1].mock


def test_the_local_command_agent_and_the_synthetic_human_propose_config_changes():
    ctx = _ctx()
    out = local_agent.answer(proposers.prompt(ctx))
    src, change = proposers.parse_reply(out)
    assert change.startswith("features") and proposers.read_config(src)["features"] == "square"
    assert local_agent.answer("no code here") == ""
    h = players.SyntheticHuman()
    seen = []
    while (c := h.propose(ctx)) is not None:
        seen.append(c.change)
    assert seen and "synthetic" in players.SyntheticHuman.LABEL


def test_play_builds_the_prompt_from_what_the_player_may_see(tmp_path):
    t = artask.load(TASK)
    g = Game.create(tmp_path / "g", TASK, title="prompt", judge=FakeJudge(t))
    pid = g.join("ada")["player"]

    class Spy:
        name = "spy"

        def __init__(self):
            self.ctx = []

        def propose(self, ctx):
            self.ctx.append(ctx)
            return proposers.Candidate({"train.py": ctx.best.replace("CONFIG = {", "# score: 0.8 final 0.8\nCONFIG = {", 1)}, "spy", "c")
    s = Spy()
    players.play(g, pid, s)
    players.play(g, pid, s)
    second = s.ctx[1]
    assert "# score: 0.8" in second.best and second.history[0]["decision"] == "scored"     # its own best, its own history
    assert "0.8" in " ".join(second.history[0]["reasons"])                                  # the shown score, never a raw one
