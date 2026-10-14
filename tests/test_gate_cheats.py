"""Gate's cheat checks on a diff: the local rules, and REFEREE's library used when it is installed."""
from __future__ import annotations

import types

import pytest

from knos.gate import cheatlib, config

CFG = config.loads("""
version: 1
hidden_tests:
  sha256: %s
  command: pytest tests/hidden
  into: tests/hidden
public_tests:
  command: pytest
scope:
  allow: ["src/**", "README.md", "tests/**"]
  deny: ["src/vendor/**"]
protect: ["data/**"]
core: ["src/core/**"]
""" % ("b" * 64))


def diff(*files):
    out = []
    for path, kind in files:
        out.append(f"diff --git a/{path} b/{path}")
        if kind == "added":
            out += ["new file mode 100644", "--- /dev/null", f"+++ b/{path}", "@@ -0,0 +1 @@", "+x = 1"]
        elif kind == "removed":
            out += ["deleted file mode 100644", f"--- a/{path}", "+++ /dev/null", "@@ -1 +0,0 @@", "-x = 1"]
        else:
            out += [f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@", "-x = 1", "+x = 2"]
    return "\n".join(out) + "\n"


def cats(findings):
    return {(f["category"], f["path"]) for f in findings}


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setattr(cheatlib, "_referee", lambda: None)


def test_a_clean_fix_has_no_finding():
    f = cheatlib.scan(diff(("src/app.py", "modified")), CFG)
    assert f == [] and not cheatlib.refused(f)


def test_a_new_test_file_is_allowed():
    assert cheatlib.scan(diff(("src/app.py", "modified"), ("tests/test_new.py", "added")), CFG) == []


@pytest.mark.parametrize("path, kind, category", [
    ("tests/test_app.py", "modified", "test_edited"),
    ("tests/test_app.py", "removed", "test_edited"),
    ("lib/other.py", "modified", "out_of_scope"),
    ("src/vendor/x.py", "modified", "out_of_scope"),
    ("data/train.csv", "modified", "data_tampering"),
    ("src/core/engine.py", "modified", "core_path"),
    (".github/workflows/ci.yml", "modified", "workflow_edited"),
    (".knos/gate.yml", "modified", "sealed_tests_changed"),
    ("tests/hidden/test_shadow.py", "added", "sealed_tests_changed"),
    ("src/conftest.py", "added", "runner_tampering"),
    ("pytest.ini", "modified", "runner_tampering"),
    ("src/evil.pth", "added", "runner_tampering"),
])
def test_each_rule_refuses_its_case(path, kind, category):
    f = cheatlib.scan(diff(("src/app.py", "modified"), (path, kind)), CFG)
    assert (category, path) in cats(f), f
    assert cheatlib.refused(f)


def test_an_empty_diff_changes_nothing():
    f = cheatlib.scan("", CFG)
    assert [x["category"] for x in f] == ["no_change"]


def test_a_rename_counts_under_both_names():
    d = "diff --git a/tests/test_app.py b/src/moved.py\nsimilarity index 100%\nrename from tests/test_app.py\nrename to src/moved.py\n"
    f = cheatlib.scan(d, CFG)
    assert ("test_edited", "tests/test_app.py") in cats(f)


def test_changed_files_reads_status():
    got = cheatlib.changed_files(diff(("a.py", "added"), ("b.py", "removed"), ("c.py", "modified")))
    assert [(g["path"], g["status"]) for g in got] == [("a.py", "added"), ("b.py", "removed"), ("c.py", "modified")]


def test_globs():
    assert cheatlib.matches("src/a/b.py", "src/**")
    assert cheatlib.matches("a.py", "*.py") and not cheatlib.matches("src/a.py", "*.py")
    assert cheatlib.matches("src/x.py", "**/*.py") and cheatlib.matches("x.py", "**/*.py")


def test_referee_library_is_used_when_installed_and_gate_rules_added():
    seen = {}

    def scan_diff(text, *, base_dir=None, scope=None, core=None, terms=None):
        seen.update(scope=scope, core=core)
        return [types.SimpleNamespace(rule="hardcoded.answer", category="hardcoded_answers", path="src/app.py",
                                      detail="returns the expected constant", severity="refuse")]

    lib = types.SimpleNamespace(scan_diff=scan_diff, RULES={"hardcoded.answer": object()})
    f = cheatlib.scan(diff(("src/app.py", "modified"), ("data/x.csv", "modified")), CFG, lib=lib)
    assert ("hardcoded_answers", "src/app.py") in cats(f) and ("data_tampering", "data/x.csv") in cats(f)
    assert seen == {"scope": ["src/**", "README.md", "tests/**"], "core": ["src/core/**"]}
    assert "hardcoded.answer" in cheatlib.rules_run(lib)


# ---- review fixes: major 7 (quoted names), major 11 (a rename's old path with REFEREE's library installed) ----

def test_a_quoted_non_ascii_name_is_read_and_checked():
    d = 'diff --git "a/tests/t\\303\\251st_app.py" "b/tests/t\\303\\251st_app.py"\n--- "a/tests/t\\303\\251st_app.py"\n+++ "b/tests/t\\303\\251st_app.py"\n@@ -1 +1 @@\n-x\n+y\n'
    got = cheatlib.changed_files(d)
    assert got[0]["path"] == "tests/t\u00e9st_app.py"
    assert ("test_edited", "tests/t\u00e9st_app.py") in cats(cheatlib.scan(d, CFG))


def test_a_diff_line_that_cannot_be_read_is_refused():
    f = cheatlib.scan('diff --git garbage\n', CFG)
    assert any(x["rule"] == "gate.unreadable_path" for x in f) and cheatlib.refused(f)


def test_a_rename_out_of_a_protected_place_is_caught_with_the_library_installed():
    lib = types.SimpleNamespace(scan_diff=lambda text, **kw: [], RULES={})
    d = "diff --git a/data/train.csv b/src/train.csv\nsimilarity index 100%\nrename from data/train.csv\nrename to src/train.csv\n"
    f = cheatlib.scan(d, CFG, lib=lib)
    assert ("data_tampering", "data/train.csv") in cats(f)
    d2 = "diff --git a/tests/test_app.py b/src/moved.py\nsimilarity index 100%\nrename from tests/test_app.py\nrename to src/moved.py\n"
    assert ("test_edited", "tests/test_app.py") in cats(cheatlib.scan(d2, CFG, lib=lib))
