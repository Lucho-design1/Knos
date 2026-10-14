"""`knos verify` (knos.verify): before a pull request, the policy at the base, the cheat checks on the diff, the tests
twice in a throwaway clone, and a signed receipt. On a small real git repository; no network."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from knos import cli
from knos import verify as V
from knos.verify import receipt as R


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def proj(tmp_path):
    """A repository with a bug on main and a branch `fix` that fixes it; origin points at a GitHub name."""
    r = tmp_path / "proj"
    (r / "tests").mkdir(parents=True)
    (r / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (r / "tests" / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    (r / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
    (r / "CONTRIBUTING.md").write_text("AI-assisted contributions must be disclosed.\n", encoding="utf-8")
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "T")
    _git(r, "remote", "add", "origin", "https://github.com/octo/widgets.git")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    _git(r, "checkout", "-qb", "fix")
    (r / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(r, "commit", "-qam", "fix add")
    return r


def _fake_runner(results):
    calls = []

    def run(tree, command, timeout):
        calls.append((Path(tree), command))
        return dict(results[min(len(calls) - 1, len(results) - 1)])
    run.calls = calls
    return run


OK = {"exit": 0, "passed": 1, "failed": 0, "seconds": 0.1, "output_sha256": "0" * 64, "timed_out": False}
BAD = {**OK, "exit": 1, "passed": 0, "failed": 1}


def test_a_correct_fix_passes_with_real_tests_run_twice_and_a_signed_receipt(proj):
    r = V.verify(proj, base="main", agent="Claude Code")
    assert r["verdict"] == "pass" and r["reasons"] == []
    assert [x["exit"] for x in r["tests"]["runs"]] == [0, 0] and r["tests"]["rerun_match"] is True
    assert r["tests"]["runs"][0]["passed"] == 1 and r["tests"]["command"].startswith("python -m pytest")
    assert sys.executable not in json.dumps(r)                      # no local path of this machine in a public receipt
    assert r["repo"] == "octo/widgets" and r["commit"] == _git(proj, "rev-parse", "HEAD").strip()
    assert r["hidden"] == {"count": 0, "mode": "public tests only", "note": r["hidden"]["note"]} and "no Knos Gate" in r["hidden"]["note"]
    assert r["ai_policy"]["stance"] == "disclose" and "Claude Code" in r["ai_disclosure"]
    assert r["runner"]["attestation"].startswith("none: a local run")
    assert R.problems(r) == []
    md = R.markdown(r)
    assert "Knos verify: pass" in md and "re-run matched" in md and r["signature"]["digest"] in md


def test_a_tampered_receipt_and_a_foreign_signature_fail_the_check(proj):
    r = V.verify(proj, base="main", runner=_fake_runner([OK]))
    forged = {**r, "verdict": "pass", "tests": {**r["tests"], "runs": [{**OK, "passed": 99}]}}
    assert "digest does not match the receipt" in R.problems(forged)
    resigned = {**forged, "signature": {**r["signature"], "digest": R.digest(forged)}}
    assert R.problems(resigned) == ["signature does not verify"]
    assert R.problems({**r, "hidden": {"count": 3, "mode": "x", "names": ["test_secret"]}})[0].startswith("hidden may carry only")
    assert "unsigned" in R.problems({k: v for k, v in r.items() if k != "signature"})


def test_editing_a_test_to_pass_is_refused_by_the_cheat_checks_even_when_the_tests_pass(proj):
    _git(proj, "checkout", "-q", "main")
    _git(proj, "checkout", "-qb", "cheat")
    (proj / "tests" / "test_calc.py").write_text("def test_add():\n    pass\n", encoding="utf-8")
    _git(proj, "commit", "-qam", "make it green")
    r = V.verify(proj, base="main", runner=_fake_runner([OK]))
    rules = {f["rule"] for f in r["cheat_checks"]["findings"] if f["severity"] == "refuse"}
    assert r["verdict"] == "fail" and {"test_edited", "assertion_removed"} <= rules
    assert any("cheat checks fired" in x for x in r["reasons"])


def test_failing_tests_and_a_rerun_that_disagrees_fail(proj):
    assert V.verify(proj, base="main", runner=_fake_runner([BAD]))["verdict"] == "fail"
    r = V.verify(proj, base="main", runner=_fake_runner([OK, {**OK, "passed": 2}]))
    assert r["verdict"] == "fail" and r["tests"]["rerun_match"] is False and "the re-run did not agree with the first run" in r["reasons"]


def test_a_repository_that_bans_ai_is_refused_and_no_test_runs(proj):
    _git(proj, "checkout", "-q", "main")
    (proj / "AI_POLICY.md").write_text("We do not accept AI-generated pull requests.\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "policy")
    _git(proj, "checkout", "-qb", "agent")
    (proj / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(proj, "commit", "-qam", "fix")
    runner = _fake_runner([OK])
    r = V.verify(proj, base="main", runner=runner, human_confirmed=True)       # not even a person can override banned
    assert r["verdict"] == "refused" and runner.calls == [] and r["tests"]["runs"] == []
    assert r["ai_policy"]["stance"] == "banned" and r["ai_policy"]["untrusted"]["lines"] == ["We do not accept AI-generated pull requests."]
    assert "do not open one" in r["reasons"][0]


def test_the_policy_is_read_at_the_base_so_a_change_cannot_rewrite_it(proj):
    _git(proj, "checkout", "-q", "main")
    (proj / "AI_POLICY.md").write_text("AI-generated contributions are banned.\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "policy")
    _git(proj, "checkout", "-qb", "sneaky")
    (proj / "AI_POLICY.md").write_text("ai-contributions: allowed\n", encoding="utf-8")
    _git(proj, "commit", "-qam", "relax the policy")
    assert V.verify(proj, base="main", runner=_fake_runner([OK]))["verdict"] == "refused"


def test_a_conditional_policy_needs_the_persons_confirmation(proj):
    _git(proj, "checkout", "-q", "main")
    (proj / "AI_POLICY.md").write_text("AI-assisted pull requests without human review will be closed.\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "policy")
    _git(proj, "checkout", "-qb", "agent")
    (proj / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(proj, "commit", "-qam", "fix")
    assert V.verify(proj, base="main", runner=_fake_runner([OK]))["verdict"] == "refused"
    r = V.verify(proj, base="main", runner=_fake_runner([OK]), human_confirmed=True)
    assert r["verdict"] == "pass" and "A person confirmed" in r["ai_disclosure"]


def test_gate_scope_at_the_base_holds_the_change_to_its_paths(proj):
    _git(proj, "checkout", "-q", "main")
    (proj / ".knos").mkdir()
    (proj / ".knos" / "gate.yml").write_text("scope:\n  - tests/**\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "gate")
    _git(proj, "checkout", "-qb", "agent2")
    (proj / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _git(proj, "commit", "-qam", "fix")
    r = V.verify(proj, base="main", runner=_fake_runner([OK]))
    assert r["verdict"] == "fail" and any(f["rule"] == "out_of_scope" and f["path"] == "calc.py" for f in r["cheat_checks"]["findings"])
    assert "Knos Gate is on" in r["hidden"]["note"] and r["hidden"]["count"] == 0


def test_the_tests_get_no_token_and_the_checkout_is_not_touched(proj, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "y" * 30)
    env = V.clean_env()
    assert "GH_TOKEN" not in env and "OPENAI_API_KEY" not in env and env.get("PATH")
    runner = _fake_runner([OK])
    before = _git(proj, "status", "--porcelain")
    r = V.verify(proj, base="main", runner=runner)
    assert all(tree != proj and not tree.exists() for tree, _c in runner.calls)       # a throwaway clone, removed after
    assert _git(proj, "status", "--porcelain") == before
    text = json.dumps(r)
    assert "ghp_" not in text and "sk-" not in text


def test_counts_are_read_from_pytest_jest_and_cargo_output():
    assert V.counts("== 3 passed, 1 failed, 2 errors in 0.1s ==") == {"passed": 3, "failed": 3}
    assert V.counts("Tests:       1 failed, 4 passed, 5 total") == {"passed": 4, "failed": 1}
    assert V.counts("test result: ok. 2 passed; 0 failed\ntest result: ok. 3 passed; 1 failed") == {"passed": 5, "failed": 1}
    assert V.counts("nothing here") == {"passed": None, "failed": None}


def test_the_command_line_writes_the_receipt_prints_the_markdown_and_exits_by_verdict(proj, capsys, monkeypatch):
    cli.load()
    out = proj.parent / "receipt.json"
    assert cli.main(["verify", "--tree", str(proj), "--base", "main", "--runs", "1", "--out", str(out), "--agent", "Hermes Agent"]) == 0
    said = capsys.readouterr().out
    assert "Knos verify: pass" in said and "AI use:" in said and f"receipt: {out}" in said
    assert cli.main(["verify", "--check", str(out)]) == 0 and capsys.readouterr().out.startswith("valid")
    data = json.loads(out.read_text(encoding="utf-8"))
    data["verdict"] = "fail"
    out.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["verify", "--check", str(out)]) == 1 and "NOT valid" in capsys.readouterr().out
    assert cli.main(["verify", "--key"]) == 0 and len(capsys.readouterr().out.strip()) >= 32
    assert (Path(os.environ["KNOS_HOME"]) / "verify-key.json").stat().st_mode & 0o077 == 0 or sys.platform == "win32"
    # the default receipt lives inside .git, where it is never committed
    assert cli.main(["verify", "--tree", str(proj), "--base", "main", "--runs", "1"]) == 0
    assert (proj / ".git" / "knos" / "receipt.json").is_file() and _git(proj, "status", "--porcelain") == ""


def test_the_diff_reader_takes_git_and_plain_diffs_and_reads_content_lines_by_hunk_counts():
    from knos.verify import cheats
    git_diff = ("diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1,2 +1,1 @@\n"
                " def test_x():\n-    assert f() == 1\n"
                "diff --git a/sql/a.sql b/sql/a.sql\nnew file mode 100644\n--- /dev/null\n+++ b/sql/a.sql\n@@ -0,0 +1,2 @@\n+-- a comment\n+++x\n")
    files = cheats.parse_diff(git_diff)
    assert files["tests/test_x.py"]["removed"] == ["    assert f() == 1"] and files["sql/a.sql"]["status"] == "added"
    assert files["sql/a.sql"]["added"] == ["-- a comment", "++x"]
    plain = "--- a/tests/test_y.py\n+++ b/tests/test_y.py\n@@ -1,3 +1,2 @@\n x = 1\n--- y\n-    assert y\n"
    files = cheats.parse_diff(plain)
    assert list(files) == ["tests/test_y.py"] and files["tests/test_y.py"]["removed"] == ["-- y", "    assert y"]
    rules = {f["rule"] for f in cheats.local_scan(plain)}
    assert {"test_edited", "assertion_removed"} <= rules
