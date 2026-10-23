"""Knos Gate end to end on a small repository made here (synthetic, no network): its five cases.

    a pull request that edits tests is refused (and no test runs)
    a pull request outside scope is refused
    a correct fix passes (hidden and public tests, the re-run agrees) and gets a signed receipt
    a pull request that passes the public tests but fails the hidden ones is refused
    hidden test contents never appear in the comment, the verdict, the summary or the receipt"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from solders.keypair import Keypair

from knos.gate import run as gate_run
from knos.gate import sealed
from knos.receipt2 import core as rc

HIDDEN_LINE = "assert slug('Hello,  World!') == 'hello-world'"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture()
def repo(tmp_path):
    """base: slug() lowercases only. Public test: lowercasing. Hidden tests: punctuation and spaces too."""
    base = tmp_path / "base"
    (base / "src").mkdir(parents=True)
    (base / "tests").mkdir()
    (base / "data").mkdir()
    (base / "src" / "slugs.py").write_text("def slug(s):\n    return s.lower()\n")
    (base / "tests" / "conftest.py").write_text("import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))\n")
    (base / "tests" / "test_public.py").write_text("from slugs import slug\n\ndef test_lower():\n    assert slug('ABC') == 'abc'\n")
    (base / "data" / "words.txt").write_text("synthetic\n")
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "conftest.py").write_text("import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[2] / 'src'))\n")
    (hidden / "test_hidden_slug.py").write_text(f"from slugs import slug\n\ndef test_punct():\n    {HIDDEN_LINE}\n\n"
                                                "def test_lower():\n    assert slug('ABC') == 'abc'\n")
    bundle = sealed.pack(hidden)
    (base / ".knos").mkdir()
    (base / ".knos" / "gate.yml").write_text(f"""version: 1
hidden_tests:
  sha256: {sealed.seal(bundle)}
  into: tests/hidden
  command: {sys.executable} -m pytest -q tests/hidden
public_tests:
  command: {sys.executable} -m pytest -q tests/test_public.py
scope:
  allow: ["src/**", "tests/**"]
protect: ["data/**"]
on_fail: close
pass_label: knos-verified
""")
    git(base, "init", "-q")
    git(base, "add", "-A")
    git(base, "commit", "-qm", "base")
    bf = tmp_path / "bundle.tgz"
    bf.write_bytes(bundle)
    return {"base": base, "bundle": bf, "tmp": tmp_path}


def pr(repo, name, files: dict, removed=()):
    work = repo["tmp"] / name
    git(repo["tmp"], "clone", "-q", str(repo["base"]), str(work))
    for p, text in files.items():
        (work / p).parent.mkdir(parents=True, exist_ok=True)
        (work / p).write_text(text)
    for p in removed:
        (work / p).unlink()
    git(work, "add", "-A")
    git(work, "commit", "-qm", name)
    diff = git(work, "diff", "HEAD~1", "HEAD")
    head = git(work, "rev-parse", "HEAD").strip()
    return work, diff, head


def judge(repo, name, files, removed=(), key=None, association="NONE", pull=None):
    work, diff, head = pr(repo, name, files, removed)
    out = repo["tmp"] / f"out-{name}"
    got = gate_run.run(base=repo["base"], pr_dir=work, diff=diff, repo="owner/demo", pr=7, head=head, base_sha="b" * 40,
                       author_association=association, out=out, hidden_file=repo["bundle"], sandbox="none", keypair=key,
                       issuer_name="test", env={}, pull=pull)
    return got, out


def first_refusal(v):
    """The category of the first refusing finding: REFEREE's library names its rules its own way, the category is shared."""
    return next(f["category"] for f in v["findings"] if f.get("severity", "refuse") == "refuse")


GOOD = "import re\n\ndef slug(s):\n    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')\n"
LAZY = "def slug(s):\n    return s.lower().replace(' ', '-')\n"


def test_a_pull_request_that_edits_tests_is_refused(repo):
    got, out = judge(repo, "edit-tests", {"src/slugs.py": LAZY, "tests/test_public.py": "def test_lower():\n    pass\n"})
    v = got["verdict"]
    assert not v["passed"] and first_refusal(v) == "test_edited"
    assert v["hidden"] is None and v["public"] is None          # untrusted code was not run
    assert v["actions"]["close"] is True


def test_a_pull_request_outside_scope_is_refused(repo):
    got, _ = judge(repo, "scope", {"src/slugs.py": GOOD, "setup.py": "print('x')\n"})
    assert not got["verdict"]["passed"] and first_refusal(got["verdict"]) == "out_of_scope"


def test_data_tampering_is_refused(repo):
    got, _ = judge(repo, "data", {"src/slugs.py": GOOD, "data/words.txt": "changed\n"})
    assert "data_tampering" in {f["category"] for f in got["verdict"]["findings"]} and not got["verdict"]["passed"]


def test_a_correct_fix_passes_with_a_signed_receipt(repo):
    key = Keypair()
    got, out = judge(repo, "good", {"src/slugs.py": GOOD}, key=key)
    v = got["verdict"]
    assert v["passed"], v
    assert v["hidden"]["passed"] == 2 and v["hidden"]["total"] == 2 and v["public"]["passed"] == 1
    assert v["actions"] == {"close": False, "add_labels": ["knos-verified"], "remove_labels": ["knos-gate-failed"]}
    env = json.loads((out / "receipt.json").read_text())
    assert rc.verify(env)["valid"]
    r = env["receipt"]
    assert r["verdict"] == "passed" and r["mode"] == "hidden" and r["rerun"] == {"ran": True, "agrees": True}
    assert r["tests"]["hidden"] == {"total": 2, "passed": 2, "failed": 0, "errors": 0, "skipped": 0}
    assert (out / "receipt.html").is_file() and (out / "badge.svg").read_text().startswith("<svg")
    assert not (work := repo["tmp"] / "good" / "tests" / "hidden").exists(), work        # the hidden tests were removed


def test_passing_public_but_failing_hidden_is_refused(repo):
    got, _ = judge(repo, "lazy", {"src/slugs.py": LAZY})
    v = got["verdict"]
    assert v["public"]["passed"] == 1 and v["public"]["failed"] == 0
    assert not v["passed"] and v["rule"] == "gate.hidden_tests_failed" and v["hidden"]["failed"] == 1


def test_hidden_contents_never_appear_in_anything_gate_writes(repo):
    for name, src in (("leakcheck-good", GOOD), ("leakcheck-lazy", LAZY)):
        got, out = judge(repo, name, {"src/slugs.py": src}, key=Keypair())
        written = "".join(p.read_text(errors="replace") for p in out.rglob("*") if p.is_file())
        for needle in (HIDDEN_LINE, "Hello,  World!", "test_punct", "test_hidden_slug"):
            assert needle not in written and needle not in got["comment"], (name, needle)


def test_a_hidden_test_quoted_by_the_comment_is_never_posted(repo, monkeypatch):
    from knos.gate import report
    real = report.comment
    monkeypatch.setattr(report, "comment", lambda v, r=None, u="": real(v, r, u) + ("\n" + HIDDEN_LINE if r is not None else ""))
    got, out = judge(repo, "leakguard", {"src/slugs.py": GOOD}, key=Keypair())
    assert got["verdict"]["rule"] == "gate.leak_guard" and HIDDEN_LINE not in got["comment"]
    assert not (out / "receipt.json").exists() or HIDDEN_LINE not in (out / "receipt.json").read_text()


def test_a_wrong_seal_is_refused(repo, tmp_path):
    other = tmp_path / "o"
    other.mkdir()
    (other / "test_x.py").write_text("def test_x():\n    pass\n")
    repo["bundle"].write_bytes(sealed.pack(other))
    got, _ = judge(repo, "wrongseal", {"src/slugs.py": GOOD})
    assert got["verdict"]["rule"] == "gate.error" and "not the sealed ones" in got["verdict"]["reasons"][0]


def test_an_inside_author_is_not_judged_with_outside_only(repo):
    got, _ = judge(repo, "member", {"src/slugs.py": LAZY}, association="MEMBER")
    assert got["verdict"]["passed"] and got["verdict"]["skipped"]


def test_a_failing_bounty_claim_is_closed(repo):
    got, _ = judge(repo, "claim", {"src/slugs.py": LAZY}, pull={"title": "slug", "body": "Fixes #12"})
    assert got["verdict"]["actions"]["close"] and got["verdict"]["claims"] == [12]
