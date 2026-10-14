"""knos self: a referee change needs the founder, and a weaker referee is blocked by the red-team regression gate
(it must refuse every fixed red-team case main's referee refuses), whoever signed it."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from knos import cheats
from knos.self import config, referee_gate

ROOT = Path(__file__).resolve().parents[1]
CASES = ("python-07", "python-04", "python-17")        # runner_patch, exit_in_test_process, no_source_change


def _tree(tmp_path, name: str) -> Path:
    t = tmp_path / name
    shutil.copytree(ROOT / "src" / "knos", t / "src" / "knos", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return t


def _cases():
    return [c for c in cheats.CASES if c.id in CASES]


def test_a_weaker_referee_is_blocked_by_the_red_team_gate(tmp_path):
    weak = _tree(tmp_path, "weak")
    rules = weak / "src" / "knos" / "cheats" / "rules.py"
    text = rules.read_text()
    cut = 'Rule("runner_patch", "runner_forgery", "code that patches the test runner", check=runner_patch),'
    assert cut in text                                  # the rule stays registered; it just stops seeing anything
    rules.write_text(text.replace(cut, 'Rule("runner_patch", "runner_forgery", "code that patches the test runner", check=lambda change: []),'))
    got = referee_gate.red_team_gate(ROOT, weak, cases=_cases())
    assert got["current"]["caught"] == 3
    assert got["candidate"]["caught"] < got["current"]["caught"]
    assert "python-07" in got["newly_missed"] and got["passed"] is False
    cfg = config.load(ROOT)
    decision = referee_gate.referee_change(ROOT, weak, cfg, cases=_cases(), approval={"key": "x", "signature": "y"})
    assert decision["decision"] == "blocked" and "red-team regression" in decision["reasons"][0]


def test_an_unchanged_referee_passes_the_gate_and_a_changed_one_that_catches_as_much_still_waits_for_the_founder(tmp_path):
    same = _tree(tmp_path, "same")
    got = referee_gate.red_team_gate(ROOT, same, cases=_cases())
    assert got["passed"] and got["candidate"] == got["current"]
    assert referee_gate.referee_change(ROOT, same, config.load(ROOT), cases=_cases())["decision"] == "no_change"
    changed = _tree(tmp_path, "changed")
    extra = changed / "src" / "knos" / "cheats" / "rules.py"
    extra.write_text(extra.read_text() + "\n# a changed referee (same rules, so the same cases caught)\n")
    d = referee_gate.referee_change(ROOT, changed, config.load(ROOT), cases=_cases())
    assert d["red_team"]["passed"] and d["decision"] == "waiting"              # shadow jobs and the founder still needed


def test_only_a_founder_signature_over_the_candidate_hash_approves():
    solders = pytest.importorskip("solders.keypair")
    kp = solders.Keypair()
    key = str(kp.pubkey())
    h = "ab" * 32
    sig = str(kp.sign_message(referee_gate.approval_message(h)))
    assert referee_gate.founder_approved(h, {"key": key, "signature": sig}, [key]) == (True, "signed by the founder")
    assert referee_gate.founder_approved("cd" * 32, {"key": key, "signature": sig}, [key])[0] is False
    assert referee_gate.founder_approved(h, {"key": key, "signature": sig}, [])[0] is False      # no key listed: waits
    assert referee_gate.founder_approved(h, {"key": key, "signature": sig}, ["someone-else"])[0] is False
