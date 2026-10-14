"""The cheat library: the 63 tamper-benchmark cases, each refused by its named rule; the honest submissions of the
benchmark, none refused; the outcome rules, each on its known-bad case; and the library only grows."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from knos import cheats

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tests" / "bench_tamper"


def test_the_library_holds_the_63_tamper_cases_21_per_language_each_naming_a_rule_that_exists():
    assert len(cheats.CASES) == 63 and len({c.id for c in cheats.CASES}) == 63
    assert Counter(c.language for c in cheats.CASES) == {"python": 21, "node": 21, "ruby": 21}
    for c in cheats.CASES:
        assert c.expect and c.expect <= set(cheats.RULES), c.id
        assert c.category == cheats.RULES[_order(c)[0]].category            # the first rule named is the case's category
    # the same 21 attacks the benchmark runs, by name, in order (docs/reference/TAMPER.md counts 63 of them)
    for lang, module in (("python", "attacks.py"), ("node", "attacks_node.py"), ("ruby", "attacks_ruby.py")):
        mod = _module(module)
        assert [c.name for c in cheats.cases(language=lang)] == [n for n, _ in mod.ATTACKS], lang
        assert [c.bench[1] for c in cheats.cases(language=lang)] == [fn.__name__ for _, fn in mod.ATTACKS], lang


def _order(case):
    from knos.cheats import tamper63
    rows = {"python": tamper63._PY, "node": tamper63._NODE, "ruby": tamper63._RUBY}[case.language]
    return next(r[2] for r in rows if r[0] == case.bench[1])


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"knos_test_{name[:-3]}", BENCH / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("case", cheats.CASES, ids=[c.id for c in cheats.CASES])
def test_each_tamper_case_is_refused_by_its_rule_before_any_code_runs(case, tmp_path):
    base, pr = tmp_path / "base", tmp_path / "pr"
    cheats.build_case(case, base, pr)
    found = cheats.scan(base, pr)
    fired = {f.rule for f in found}
    assert case.expect <= fired, (case.id, sorted(fired))
    assert cheats.refused(found)
    assert case.category in cheats.categories(found)


def test_the_count_by_category_is_what_the_docs_say():
    by = Counter(c.category for c in cheats.CASES)
    doc = (ROOT / "docs" / "reference" / "REFEREE.md").read_text(encoding="utf-8")
    for cat, n in by.items():
        assert f"| {cat} | {n} |" in doc, cat
    assert sum(by.values()) == 63


def _honest():
    sys.path.insert(0, str(BENCH))
    sys.path.insert(0, str(ROOT / "scripts"))
    return _module("honest.py")


def test_no_honest_slugify_submission_is_refused_by_any_rule(tmp_path):
    """The benchmark's honest set (another algorithm, another layout, slower, tests of its own, a conftest fixture):
    a refused honest submission would be a false finding."""
    H = _honest()
    folders = {"python": "sample", "node": "sample_node", "ruby": "sample_ruby"}
    n = 0
    for key, subs in H.SLUG.items():
        for i, (name, fn) in enumerate(subs):
            base, pr = tmp_path / key / str(i) / "b", tmp_path / key / str(i) / "p"
            shutil.copytree(BENCH / folders[key], base)
            shutil.copytree(BENCH / folders[key], pr)
            fn(pr)
            found = cheats.scan(base, pr)
            assert not cheats.refused(found), (key, name, [f.to_dict() for f in found])
            n += 1
    assert n >= 25


def test_no_honest_submission_to_the_six_real_tasks_is_refused(tmp_path):
    H = _honest()
    spec = importlib.util.spec_from_file_location("knos_test_real_tasks", BENCH / "real_tasks.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    for key, task in R.TASKS.items():
        base = tmp_path / key / "base"
        R.materialise(task, base)
        for i, (name, fn) in enumerate(H.REAL):
            pr = tmp_path / key / str(i)
            shutil.copytree(base, pr)
            fn(pr, task, base)
            found = cheats.scan(base, pr)
            assert not cheats.refused(found), (key, name, [f.to_dict() for f in found])


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize("case", [c for c in cheats.CASES if c.language == "python"], ids=lambda c: c.id)
def test_a_git_diff_of_each_case_is_refused_the_same_way(case, tmp_path):
    """What Gate and the maintainer mode read: `git diff base...head`, with the base checkout beside it."""
    base, pr = tmp_path / "base", tmp_path / "pr"
    cheats.build_case(case, base, pr)
    repo = tmp_path / "repo"
    shutil.copytree(base, repo)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    for p in list(repo.iterdir()):
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(pr, repo, dirs_exist_ok=True)
    _git(repo, "add", "-A")
    diff = _git(repo, "diff", "--cached", "-M", "HEAD")
    found = cheats.scan_diff(diff, base_dir=base)
    assert cheats.refused(found) and case.expect <= {f.rule for f in found}, (case.id, [f.rule for f in found])


def test_scope_and_core_paths():
    diff = ("diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
            "diff --git a/deploy/k.sh b/deploy/k.sh\n--- a/deploy/k.sh\n+++ b/deploy/k.sh\n@@ -1 +1 @@\n-a\n+b\n"
            "diff --git a/tests/test_new.py b/tests/test_new.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_new.py\n"
            "@@ -0,0 +1 @@\n+def test_x():\n+    assert 1 + 1 == 2\n")
    found = cheats.scan_diff(diff, scope=["src/**"], core=["deploy/**"])
    rules = {(f.rule, f.path) for f in found}
    assert ("out_of_scope", "deploy/k.sh") in rules and ("core_path_touched", "deploy/k.sh") in rules
    assert not any(p in ("src/a.py", "tests/test_new.py") for r, p in rules if r == "out_of_scope")   # a new test is allowed
    assert not cheats.refused(cheats.scan_diff(diff, scope=["src/**", "deploy/**"]))


def test_assertions_and_detector_markers_removed_from_an_existing_test_are_refused():
    diff = ("diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1,4 +1,2 @@\n"
            " def test_a():\n-    assert f(1) == 2\n-    assert f(2) == 3  # knos:detector\n+    pass\n")
    rules = {f.rule for f in cheats.scan_diff(diff, terms={"test_dirs": ["tests"]})}
    assert {"assertion_removed", "detector_marker_removed", "test_edited"} <= rules


def test_one_literal_shared_with_a_test_is_not_hardcoding(tmp_path):
    """An error message a test matches is fine; an input and its expected answer from the same test line is not."""
    base = tmp_path / "b"
    (base / "tests").mkdir(parents=True)
    (base / "tests" / "test_p.py").write_text('import p\n\ndef test_bad():\n    assert p.parse("12abc") == "bad input"\n', encoding="utf-8")
    (base / "p.py").write_text("def parse(s):\n    return s\n", encoding="utf-8")
    pr = tmp_path / "p"
    shutil.copytree(base, pr)
    (pr / "p.py").write_text('def parse(s):\n    if not s.isdigit():\n        return "bad input"\n    return s\n', encoding="utf-8")
    assert not cheats.refused(cheats.scan(base, pr))
    (pr / "p.py").write_text('def parse(s):\n    if s == "12abc":\n        return "bad input"\n    return s\n', encoding="utf-8")
    assert "hardcoded_answers" in {f.rule for f in cheats.scan(base, pr)}


FUNDED = {"spec_hash": "a" * 64, "window": {"start": "2026-10-01", "end": "2026-10-31"}, "salt": "s1",
          "control_share": 0.2, "measurement_commit": "c" * 40, "data_hashes": {"data/tickets.csv": "d" * 64}}


@pytest.mark.parametrize("change, rule", [
    ({"spec_hash": "b" * 64}, "outcome_spec_hash_changed"),
    ({"window": {"start": "2026-10-01", "end": "2026-11-30"}}, "outcome_window_changed"),
    ({"salt": "s2"}, "outcome_salt_changed"),
    ({"control_share": 0.12}, "outcome_control_drift"),
    ({"measurement_commit": "e" * 40}, "outcome_measurement_code_drift"),
    ({"data_hashes": {"data/tickets.csv": "f" * 64}}, "outcome_data_tampered"),
    ({"data_hashes": {}}, "outcome_data_tampered"),
])
def test_each_outcome_rule_refuses_its_known_bad_case(change, rule):
    assert cheats.scan_outcome(FUNDED, dict(FUNDED)) == []
    found = cheats.scan_outcome(FUNDED, {**FUNDED, **change})
    assert [f.rule for f in found] == [rule] and cheats.refused(found)
    assert found[0].category == cheats.RULES[rule].category


def test_control_share_within_tolerance_and_new_data_are_not_cheats():
    now = {**FUNDED, "control_share": 0.21, "data_hashes": {**FUNDED["data_hashes"], "data/later.csv": "0" * 64}}
    assert cheats.scan_outcome(FUNDED, now) == []


def test_the_library_only_grows_and_every_rule_is_well_formed():
    with pytest.raises(ValueError):
        cheats.add_rule(cheats.Rule("runner_patch", "runner_forgery", "again"))
    with pytest.raises(ValueError):
        cheats.Rule("x_new_rule", "no_such_category", "x")
    assert set(r.category for r in cheats.RULES.values()) <= set(cheats.CATEGORIES)
    for r in cheats.rules(kind="change"):          # every change rule refuses at least one known case or has its own test here
        named = {x for c in cheats.CASES for x in c.expect}
        assert r.id in named or r.id in {"test_edited", "unrestored_test_config", "out_of_scope", "core_path_touched",
                                         "assertion_removed", "detector_marker_removed"}, r.id


def test_red_team_catches_every_known_case_and_a_weaker_scanner_does_not():
    got = cheats.red_team()
    assert got == {"caught": 63, "total": 63, "missed": []}
    weaker = cheats.red_team(lambda b, p: [f for f in cheats.scan(b, p) if f.rule != "hardcoded_answers"])
    assert weaker["caught"] == 60 and sorted(weaker["missed"]) == ["node-20", "python-20", "ruby-20"]


# ---- review findings 6-9 (v0.3.29 fix phase) ---------------------------------------------------------------------------

def test_the_repositorys_language_comes_from_the_base_never_from_what_the_change_adds(tmp_path):
    """Finding 6: adding one .js or .rb file must not turn a Python repository's tests/ into unprotected paths."""
    base = tmp_path / "b"
    (base / "tests").mkdir(parents=True)
    (base / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    pr = tmp_path / "p"
    shutil.copytree(base, pr)
    (pr / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    for extra in ("helper.js", "x.rb", "package.json", "Gemfile"):
        (pr / extra).write_text("{}\n", encoding="utf-8")
    assert cheats.library.guess_runner(base, ["helper.js", "x.rb"]) == "python"
    assert {"test_edited", "assertion_removed"} <= {f.rule for f in cheats.scan(base, pr)}
    diff = ("diff --git a/x.rb b/x.rb\nnew file mode 100644\n--- /dev/null\n+++ b/x.rb\n@@ -0,0 +1 @@\n+puts 1\n"
            "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n"
            "@@ -1,2 +1,2 @@\n def test_a():\n-    assert 1 == 1\n+    pass\n")
    assert "test_edited" in {f.rule for f in cheats.scan_diff(diff, base_dir=base)}


def test_a_git_quoted_non_ascii_path_is_read_and_its_rules_apply():
    """Finding 7: `git diff` C-quotes such names ("t\\303\\251st..."); they were skipped and bypassed every rule."""
    diff = ('diff --git "a/tests/t\\303\\251st_a.py" "b/tests/t\\303\\251st_a.py"\nindex 1..2 100644\n'
            '--- "a/tests/t\\303\\251st_a.py"\n+++ "b/tests/t\\303\\251st_a.py"\n@@ -1,2 +1,2 @@\n def test_a():\n'
            '-    assert f(1) == 2\n+    assert True\n'
            'diff --git a/sp ace/conftest.py b/sp ace/conftest.py\nnew file mode 100644\n--- /dev/null\n'
            '+++ b/sp ace/conftest.py\t2026-10-13\n@@ -0,0 +1,2 @@\n+import sys\n+sys.exit(0)\n')
    files = {f.path: f for f in cheats.parse_diff(diff)}
    assert set(files) == {"tests/tést_a.py", "sp ace/conftest.py"} and files["sp ace/conftest.py"].status == "added"
    rules = {(f.rule, f.path) for f in cheats.scan_diff(diff, terms={"test_dirs": ["tests"]})}
    assert ("test_edited", "tests/tést_a.py") in rules and ("trivial_assertion", "tests/tést_a.py") in rules
    assert ("exit_in_test_process", "sp ace/conftest.py") in rules
    assert cheats.library.unquote_path('"a\\"b\\\\c\\tx"') == 'a"b\\c\tx'


def test_a_file_with_no_diff_git_line_is_still_read_and_hunk_content_is_never_taken_for_a_header():
    diff = ("--- a/conftest.py\t2026-10-13 10:00\n+++ b/conftest.py\t2026-10-13 10:01\n@@ -0,0 +1,2 @@\n+import os\n+os._exit(0)\n"
            "diff --git a/q.sql b/q.sql\n--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,2 @@\n--- a comment that looks like a header\n"
            "+++ another\n x\n")
    files = {f.path: f for f in cheats.parse_diff(diff)}
    assert set(files) == {"conftest.py", "q.sql"}
    assert files["q.sql"].removed == ["-- a comment that looks like a header"] and files["q.sql"].added == ["++ another"]
    assert "exit_in_test_process" in {f.rule for f in cheats.scan_diff(diff)}
    bad = cheats.scan_diff("diff --git nonsense\n+x\n")
    assert cheats.refused(bad) and bad[0].rule == "rule_error" and bad[0].category == "rule_error"


def _pkg_repo(tmp: Path) -> Path:
    base = tmp / "b"
    base.mkdir()
    (base / "package.json").write_text('{\n  "name": "x",\n  "scripts": {\n    "test": "node --test"\n  },\n'
                                        '  "dependencies": {\n    "left-pad": "1.0.0"\n  }\n}\n', encoding="utf-8")
    return base


def test_a_package_json_diff_is_flagged_only_when_it_touches_the_test_script(tmp_path):
    """Finding 8: in a diff the new whole text is not known, so every package.json edit used to look like a changed
    test script, and close mode closed honest pull requests."""
    base = _pkg_repo(tmp_path)
    bump = ('diff --git a/package.json b/package.json\n--- a/package.json\n+++ b/package.json\n@@ -6,3 +6,3 @@\n'
            '   "dependencies": {\n-    "left-pad": "1.0.0"\n+    "left-pad": "1.3.0"\n   }\n')
    assert not cheats.refused(cheats.scan_diff(bump, base_dir=base, claim=False))
    script = ('diff --git a/package.json b/package.json\n--- a/package.json\n+++ b/package.json\n@@ -3,3 +3,3 @@\n'
              '   "scripts": {\n-    "test": "node --test"\n+    "test": "node -e 0"\n   },\n')
    assert "test_script_changed" in {f.rule for f in cheats.scan_diff(script, base_dir=base, claim=False)}


def test_a_rule_that_crashes_refuses_instead_of_passing_silently(monkeypatch):
    """Finding 9: `except Exception: continue` let a cheat through by making a rule crash."""
    def boom(change):
        raise RuntimeError("cannot read this")
    monkeypatch.setitem(cheats.RULES, "skip_added", cheats.Rule("skip_added", "test_edited", "x", check=boom))
    found = cheats.scan_diff("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
    errs = [f for f in found if f.rule == "rule_error"]
    assert errs and errs[0].severity == "refuse" and "skip_added" in errs[0].detail and cheats.refused(found)
