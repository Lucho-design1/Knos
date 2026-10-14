"""knos self: the loop's state on a real git repository: the trusted referee checkout is main's and never moves, the
loop branch is local, and one command rolls a version (and its descendants) back off it."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from knos import record
from knos.self.loop import Loop, LoopError

ROOT = Path(__file__).resolve().parents[1]
GIT = ["git", "-c", "user.name=knos-self-test", "-c", "user.email=self-test@knos.invalid", "-c", "commit.gpgsign=false"]


class Store:
    """Stands in for Sibyl's store here (the loop's real runs use Sibyl's own)."""

    def put(self, *a, **k):
        return None

    def journal(self, **k):
        return None

    def set_reference(self, *a, **k):
        return None


def _git(repo, *args) -> str:
    return subprocess.run([*GIT, "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src" / "knos").mkdir(parents=True)
    for f in ("targets.yml", "CODEOWNERS"):
        shutil.copy2(ROOT / f, r / f)
    shutil.copy2(ROOT / "src" / "knos" / "judge.py", r / "src" / "knos" / "judge.py")
    for d in ("referee", "cheats"):
        shutil.copytree(ROOT / "src" / "knos" / d, r / "src" / "knos" / d, ignore=shutil.ignore_patterns("__pycache__"))
    (r / "a.txt").write_text("0\n")
    _git(tmp_path, "init", "-q", "-b", "main", str(r))
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "main")
    commits = []
    for i in (1, 2):
        (r / "a.txt").write_text(f"{i}\n")
        _git(r, "commit", "-q", "-am", f"v{i}")
        commits.append(_git(r, "rev-parse", "HEAD"))
    _git(r, "checkout", "-q", "main")
    _git(r, "reset", "-q", "--hard", "HEAD~2")
    return r, commits


def test_init_makes_the_referee_checkout_and_v0_and_a_local_branch(repo, tmp_path):
    r, _ = repo
    lp = Loop(r, tmp_path / "state", branch="self-loop-test", record_store=Store())
    root = lp.init()
    main = _git(r, "rev-parse", "main")
    assert root["id"] == "v0" and root["commit"] == main and root["decision"] == "root"
    assert _git(lp.main_dir, "rev-parse", "HEAD") == main
    assert _git(r, "rev-parse", "self-loop-test") == main
    assert _git(r, "remote") == ""                                        # nothing to push to
    lp.init()                                                             # twice: nothing new
    assert [e["kind"] for e in record.entries(tmp_path / "state" / "record")] == ["claim"]


def test_one_command_rolls_a_version_and_its_descendants_back(repo, tmp_path):
    r, (c1, c2) = repo
    lp = Loop(r, tmp_path / "state", branch="self-loop-test", record_store=Store())
    lp.init()
    lp.archive.add({"id": "v1", "parent": "v0", "decision": "canary", "target": "mcp-cold-start", "commit": c1, "metric": 90})
    lp.archive.add({"id": "v2", "parent": "v1", "decision": "canary", "target": "mcp-cold-start", "commit": c2, "metric": 80})
    _git(r, "branch", "-f", "self-loop-test", c2)
    got = lp.rollback("v1", reason="the audit tier failed")
    assert got["rolled_back"] == ["v1", "v2"]
    assert _git(r, "rev-parse", "self-loop-test") == lp.archive.nodes[0]["commit"]
    assert lp.archive.get("v2")["decision"] == "rolled_back"
    assert record.entries(tmp_path / "state" / "record")[-1]["payload"]["decision"] == "rolled_back"
    with pytest.raises(LoopError):
        lp.rollback("v0")


def test_only_open_product_targets_take_candidates(repo, tmp_path):
    r, _ = repo
    lp = Loop(r, tmp_path / "state", branch="self-loop-test", record_store=Store())
    lp.init()
    with pytest.raises(LoopError, match="referee"):
        lp.run("red-team-catch-rate", "main")
    with pytest.raises(LoopError, match="open"):
        lp.run("cli-cold-start", "main")


def test_a_refused_parent_a_judged_commit_and_an_edited_referee_checkout_are_refused_before_judging(repo, tmp_path):
    r, (c1, c2) = repo
    lp = Loop(r, tmp_path / "state", branch="self-loop-test", record_store=Store())
    lp.init()
    lp.archive.add({"id": "v1", "parent": "v0", "decision": "refused", "target": "mcp-cold-start", "commit": c1})
    lp.archive.add({"id": "v2", "parent": "v0", "decision": "canary", "target": "mcp-cold-start", "commit": c2})
    lp.archive.save()
    with pytest.raises(LoopError, match="only an accepted version"):
        lp.run("mcp-cold-start", c2, parent="v1")
    with pytest.raises(LoopError, match="judged already"):
        lp.run("mcp-cold-start", c2, parent="v0")
    (lp.main_dir / "src" / "knos" / "cheats" / "rules.py").write_text("RULES = {}\n")
    with pytest.raises(LoopError, match="local changes"):
        lp.run("mcp-cold-start", c1, parent="v0")
    assert lp.archive.nodes[0]["loop_hash"]                      # pinned at init
