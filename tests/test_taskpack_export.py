"""knos taskpack: a merged issue + pull request exported as a sealed, verified task package, and graded."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from knos.taskpack import atropos, export as ex, grade as gr

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software...\n"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
TEST = "from swapcase import swap\n\n\ndef test_swap():\n    assert swap('aB') == 'Ab'\n    assert swap('') == ''\n"
FIX = "def swap(text):\n    return text.swapcase()\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=ENV).stdout.strip()


def _repo(tmp: Path, *, licence: str | None = MIT, opt_in: bool = True, with_tests: bool = True, already: bool = False) -> tuple[Path, str]:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("# demo\n", newline="\n")
    (repo / "pytest.ini").write_text("[pytest]\n", newline="\n")
    if licence:
        (repo / "LICENSE").write_text(licence, newline="\n")
    if opt_in:
        (repo / ".knos").mkdir()
        (repo / ".knos" / "taskpack.yml").write_text("export: true\n", newline="\n")
    (repo / "swapcase.py").write_text(FIX if already else "def swap(text):\n    raise NotImplementedError\n", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "swapcase.py").write_text(FIX + "\n# fixed\n", newline="\n")
    if with_tests:
        (repo / "tests").mkdir()
        (repo / "tests" / "test_swapcase.py").write_text(TEST, newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix #3")
    return repo, _git(repo, "rev-parse", "HEAD")


ISSUE = {"number": 3, "title": "swap the case of a text", "body": "swap('aB') should give 'Ab'."}
PR = {"repo": "octo/demo", "number": 4}


@pytest.fixture()
def pack(tmp_path):
    repo, merge = _repo(tmp_path)
    folder = ex.export(repo, merge=merge, pr=PR, issue=ISSUE, out=tmp_path / "out")
    return repo, folder


def test_export_seals_the_hidden_tests_and_proves_the_task_is_real(pack):
    repo, folder = pack
    m = ex.load(folder)
    assert m["task_id"] == "knos-task-" + m["spec_sha256"][:16] and ex.verify(folder) == []
    assert m["verified"]["base_fails"] and m["verified"]["merge_passes"] and "1 passed" in m["verified"]["merge_summary"]
    assert m["licence"]["spdx"] == "MIT" and m["licence"]["sellable"] and m["opt_in"]["by"] == "the repository"
    assert m["scope"]["allowed"] == [""] and m["sealed"]["tests_count"] == 1 and m["source"]["issue"] == 3
    public = "".join(p.read_text() for p in (folder / "public").iterdir())
    assert "test_swapcase" not in public and "assert swap" not in public                  # no hidden test's name or content
    assert "swap the case" in (folder / "public" / "statement.md").read_text()
    assert ex.untar(ex.sealed(folder, "tests.tar")) == {"tests/test_swapcase.py": TEST.encode()}
    assert "fee" in m and m["sale"] == "nothing here offers or sells a task package"
    assert _git(repo, "status", "--porcelain") == ""                                      # the clone was only read


def test_a_changed_sealed_file_or_manifest_does_not_verify(pack):
    _repo_dir, folder = pack
    tar = folder / "sealed" / "tests.tar"
    tar.write_bytes(tar.read_bytes().replace(b"'Ab'", b"'AB'"))
    assert any("tests.tar does not hash" in w for w in ex.verify(folder))
    m = json.loads((folder / "public" / "task.json").read_text())
    m["scope"]["allowed"] = ["anything/"]
    (folder / "public" / "task.json").write_text(json.dumps(m), newline="\n")
    assert any("spec_sha256" in w for w in ex.verify(folder))


@pytest.mark.parametrize("kw, words", [
    ({"opt_in": False}, "no maintainer opt-in"),
    ({"with_tests": False}, "nothing to seal"),
    ({"already": True}, "already pass before the fix"),
])
def test_export_refuses(tmp_path, kw, words):
    repo, merge = _repo(tmp_path, **kw)
    with pytest.raises(ex.Refused, match=words):
        ex.export(repo, merge=merge, pr=PR, issue=ISSUE, out=tmp_path / "out")


def test_the_maintainer_flag_opts_in_and_no_licence_is_not_sellable(tmp_path):
    repo, merge = _repo(tmp_path, licence=None, opt_in=False)
    folder = ex.export(repo, merge=merge, pr=PR, issue=ISSUE, out=tmp_path / "out", opt_in_flag=True, who="maint")
    m = ex.load(folder)
    assert m["opt_in"] == {"how": "--opt-in given by the maintainer who ran the export", "by": "maint"}
    assert m["licence"]["sellable"] is False and "no licence file" in m["licence"]["why"]


def test_an_encrypted_package_needs_its_key(tmp_path):
    repo, merge = _repo(tmp_path)
    folder = ex.export(repo, merge=merge, pr=PR, issue=ISSUE, out=tmp_path / "out", encrypt=True)
    assert not (folder / "sealed" / "tests.tar").exists() and (folder / "sealed" / "tests.tar.enc").is_file()
    assert not any(p.suffix == ".key" for p in folder.rglob("*"))                     # the key is never inside the package
    assert ex.verify(folder) == []
    key = ex.key_of(folder)
    (folder.parent / f"{folder.name}.key").unlink()                                    # the key travels apart from the package
    assert any("no key" in w for w in ex.verify(folder))
    assert ex.verify(folder, key) == []
    assert any("cannot be opened" in w for w in ex.verify(folder, bytes(32)))


def _patch(repo: Path, edit) -> str:
    """A candidate patch against the base commit, made in a scratch clone."""
    work = repo.parent / f"cand{len(list(repo.parent.iterdir()))}"
    subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True, env=ENV)
    _git(work, "checkout", "-q", "HEAD~1")
    edit(work)
    _git(work, "add", "-A")
    return _git(work, "diff", "--cached", "--binary") + "\n"


def test_grading_rewards_a_real_fix_and_refuses_cheats(pack):
    repo, folder = pack
    good = _patch(repo, lambda w: (w / "swapcase.py").write_text("def swap(t):\n    return ''.join(c.lower() if c.isupper() else c.upper() for c in t)\n"))
    got = gr.grade(folder, repo, good)
    assert got == {"task_id": ex.load(folder)["task_id"], "reward": 1.0, "passed": True, "cheats": [], "tests": {"count": 1, "summary": "1 passed"}}
    wrong = _patch(repo, lambda w: (w / "swapcase.py").write_text("def swap(t):\n    return t.upper()\n"))
    got = gr.grade(folder, repo, wrong)
    assert got["reward"] == 0.0 and not got["passed"] and "test_swapcase" not in json.dumps(got) and "assert" not in json.dumps(got)

    def edit_tests(w):
        (w / "swapcase.py").write_text(FIX, newline="\n")
        (w / "tests").mkdir()
        (w / "tests" / "test_swapcase.py").write_text("def test_swap():\n    pass\n", newline="\n")
    got = gr.grade(folder, repo, _patch(repo, edit_tests))
    assert got["reward"] == -1.0 and {c["rule"] for c in got["cheats"]} >= {"test_edited"}

    def out_of_scope(w):
        (w / "swapcase.py").write_text(FIX, newline="\n")
        (w / "lib").mkdir()
        (w / "lib" / "x.py").write_text("x = 1\n", newline="\n")
    got = gr.grade(folder, repo, _patch(repo, out_of_scope))
    assert got["reward"] == -1.0 and {c["rule"] for c in got["cheats"]} >= {"out_of_scope"}
    got = gr.grade(folder, repo, _patch(repo, lambda w: (w / ".knos" / "taskpack.yml").write_text("export: false\n", newline="\n")))
    assert {c["rule"] for c in got["cheats"]} >= {"workflow_edited"}
    assert gr.grade(folder, repo, "")["cheats"] == [{"rule": "no_change", "path": ""}]
    # a header git reads without a `diff --git` line still names its file: a root conftest.py is a test file
    sneaky = ("--- /dev/null" + chr(9) + "2026-01-01 00:00:00" + chr(10) + "+++ b/conftest.py" + chr(9) + "2026-01-01 00:00:00" + chr(10)
              + "@@ -0,0 +1,2 @@" + chr(10) + "+import pytest" + chr(10) + "+pytest.skip('x', allow_module_level=True)" + chr(10))
    got = gr.grade(folder, repo, sneaky)
    assert got["reward"] == -1.0 and {c["rule"] for c in got["cheats"]} >= {"test_edited"}
    assert gr.grade(folder, repo, "this is not a patch" + chr(10))["cheats"] == [{"rule": "patch_unreadable", "path": ""}]
    # the reference fix the package seals passes its own grading
    assert gr.grade(folder, repo, ex.sealed(folder, "reference.patch").decode())["reward"] == 1.0


def test_rows_for_a_training_environment_and_the_referee_spec(pack, tmp_path):
    repo, folder = pack
    out = tmp_path / "rows.jsonl"
    assert atropos.write_jsonl([folder], out) == 1
    r = json.loads(out.read_text())
    assert r["id"] == ex.load(folder)["task_id"] and "swap the case" in r["prompt"] and r["hidden_tests"] == 1 and "assert swap" not in out.read_text()
    assert str(folder) not in out.read_text() and "pack" not in r                     # a solver given the rows cannot reach the sealed files
    assert atropos.score(r, folder, repo, ex.sealed(folder, "reference.patch").decode()) == 1.0
    spec = atropos.referee_spec(folder)
    assert spec["spec_hash"] == ex.load(folder)["spec_sha256"] and spec["cheat_rules"] == list(ex.CHEAT_RULES)


def test_the_fee_split_comes_from_money_s_api(monkeypatch):
    import knos
    monkeypatch.delitem(sys.modules, "knos.money", raising=False)
    monkeypatch.delattr(knos, "money", raising=False)
    real = __import__

    def no_money(name, *a, **k):
        if name == "money" or name.startswith("knos.money"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr("builtins.__import__", no_money)
    assert ex.fee_terms(10_000_000)["status"] == "knos.money is not in this install"
    monkeypatch.setattr("builtins.__import__", real)
    cfg = types.SimpleNamespace(task_package=lambda price: {"maintainer": price * 9 // 10, "knos": price - price * 9 // 10, "fee_bps": 1000})
    fees_config = types.SimpleNamespace(load=lambda: cfg)
    money = types.ModuleType("knos.money")
    money.fees_config = fees_config
    monkeypatch.setitem(sys.modules, "knos.money", money)
    got = ex.fee_terms(10_000_000)
    assert got["status"] == "computed" and got["maintainer"] + got["knos"] == 10_000_000 and got["fee_bps"] == 1000
    assert ex.fee_terms(None)["status"].startswith("no price")


def test_the_command_exports_offline_and_verifies(tmp_path):
    from typer.testing import CliRunner

    from knos import cli
    repo, merge = _repo(tmp_path)
    run = CliRunner().invoke
    got = run(cli.app, ["taskpack", "export", "octo/demo#4", "--repo-dir", str(repo), "--merge", merge, "--issue", "3",
                        "--issue-title", "swap", "--out", str(tmp_path / "out")])
    assert got.exit_code == 0, got.output
    folder = next((tmp_path / "out").iterdir())
    assert run(cli.app, ["taskpack", "verify", str(folder)]).exit_code == 0
    assert run(cli.app, ["taskpack", "export", "not-a-ref", "--repo-dir", str(repo), "--merge", merge]).exit_code == 1
