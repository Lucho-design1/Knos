"""Proposers: the deterministic default needs no key or network; any agent can be plugged in behind a command."""
from __future__ import annotations

import subprocess

import pytest

from knos.autoresearch import __main__ as cli
from knos.autoresearch import proposers
from test_autoresearch_loop import EXAMPLE

BASE = (EXAMPLE / "train.py").read_text(encoding="utf-8")


def ctx(best=BASE, history=()):
    return proposers.Context("program", "idea", "train.py", best, list(history))


def test_config_round_trips_and_only_the_block_changes():
    cfg = proposers.read_config(BASE)
    assert cfg["features"] == "linear"
    new = proposers.write_config(BASE, dict(cfg, lr=0.2))
    assert proposers.read_config(new)["lr"] == 0.2
    assert new.replace("'lr': 0.2", "'lr': 0.05") == BASE


def test_the_local_proposer_tries_features_first_and_never_repeats():
    p = proposers.LocalProposer(0)
    first = p.propose(ctx())
    assert first.change == "features: 'linear' -> 'square'" and first.agent == "local-deterministic"
    seen = {first.files["train.py"]}
    for _ in range(30):
        c = p.propose(ctx())
        if c is None:
            break
        assert c.files["train.py"] not in seen
        seen.add(c.files["train.py"])
    else:
        pytest.fail("the proposer never ran out of neighbours")


def test_the_local_proposer_is_deterministic_per_seed():
    def seq(seed):
        p = proposers.LocalProposer(seed)
        return [p.propose(ctx()).change for _ in range(5)]
    assert seq(3) == seq(3)


def test_a_command_agent_gets_the_prompt_and_its_python_block_is_taken():
    got = {}

    def fake(argv, input, **kw):
        got["argv"], got["prompt"] = argv, input
        return subprocess.CompletedProcess(argv, 0, "Sure.\n```python\n# change: wider features\nCONFIG = {}\n```\n", "")

    p = proposers.CommandProposer("claude -p", runner=fake)
    c = p.propose(ctx(history=[{"iteration": 1, "change": "x", "decision": "discarded", "reasons": [], "reported": {"val_accuracy": 0.5}}]))
    assert got["argv"] == ["claude", "-p"] and "program" in got["prompt"] and "#1 x -> discarded" in got["prompt"]
    assert "hidden scores are never shown" in got["prompt"]
    assert c.files == {"train.py": "# change: wider features\nCONFIG = {}\n"} and c.change == "wider features" and c.agent == "cmd:claude"


def test_a_failing_command_agent_proposes_nothing():
    p = proposers.CommandProposer("agent", runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "no key"))
    assert p.propose(ctx()) is None


def test_from_spec():
    assert isinstance(proposers.from_spec("local"), proposers.LocalProposer)
    assert isinstance(proposers.from_spec("cmd:codex exec -"), proposers.CommandProposer)
    with pytest.raises(ValueError):
        proposers.from_spec("gpt")


def test_the_cli_refuses_a_bad_task(tmp_path, capsys):
    assert cli.main(["run", str(tmp_path)]) == 2
    assert "task.json" in capsys.readouterr().err
