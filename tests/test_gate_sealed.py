"""Sealed hidden tests: a deterministic bundle, held to its seal, unpacked safely; only counts come out of a run."""
from __future__ import annotations

import gzip
import io
import os
import sys
import tarfile
from pathlib import Path

import pytest

from knos.gate import sealed


def _suite(root):
    (root / "sub").mkdir(parents=True)
    (root / "test_hidden_one.py").write_text("def test_a():\n    assert 'hidden-secret-assertion-text' != ''\n")
    (root / "sub" / "data.txt").write_text("fixture line that is long enough\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"junk")
    return root


def test_pack_is_deterministic_and_skips_caches(tmp_path):
    a = sealed.pack(_suite(tmp_path / "a"))
    os.utime(tmp_path / "a" / "test_hidden_one.py", (1, 1))
    b = sealed.pack(tmp_path / "a")
    assert a == b and sealed.seal(a) == sealed.seal(b)
    names = tarfile.open(fileobj=io.BytesIO(a), mode="r:gz").getnames()
    assert names == ["sub/data.txt", "test_hidden_one.py"]


def test_secret_roundtrip_and_unpack(tmp_path):
    bundle = sealed.pack(_suite(tmp_path / "s"))
    back = sealed.decode(sealed.encode(bundle))
    got = sealed.unpack(back, tmp_path / "out", sealed.seal(bundle))
    assert sorted(got) == ["sub/data.txt", "test_hidden_one.py"]
    with pytest.raises(sealed.Refused, match="not base64"):
        sealed.decode("%%%")


def test_a_bundle_that_is_not_the_sealed_one_is_refused(tmp_path):
    bundle = sealed.pack(_suite(tmp_path / "s"))
    with pytest.raises(sealed.Refused, match="not the sealed ones"):
        sealed.unpack(bundle, tmp_path / "out", "0" * 64)
    assert not (tmp_path / "out" / "test_hidden_one.py").exists()


def _tar(members):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as t:
        for info, data in members:
            t.addfile(info, io.BytesIO(data) if data is not None else None)
    return gzip.compress(raw.getvalue())


@pytest.mark.parametrize("name, kind", [("../escape.py", tarfile.REGTYPE), ("/abs.py", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)])
def test_unsafe_members_are_refused(tmp_path, name, kind):
    info = tarfile.TarInfo(name)
    info.type = kind
    data = b"x" if kind == tarfile.REGTYPE else None
    if data:
        info.size = 1
    else:
        info.linkname = "/etc/passwd"
    bundle = _tar([(info, data)])
    with pytest.raises(sealed.Refused):
        sealed.unpack(bundle, tmp_path / "out", sealed.seal(bundle))


def test_pack_refuses_links(tmp_path):
    root = _suite(tmp_path / "s")
    try:
        (root / "l").symlink_to(root / "test_hidden_one.py")
    except OSError:
        pytest.skip("no symlinks here")
    with pytest.raises(sealed.Refused, match="link"):
        sealed.pack(root)


def test_counts_only_from_junit(tmp_path):
    x = tmp_path / "r.xml"
    x.write_text('<testsuites><testsuite><testcase name="test_secret_name"/><testcase name="b"><failure message="secret msg"/></testcase>'
                 '<testcase name="c"><skipped/></testcase><testcase name="d"><error/></testcase></testsuite></testsuites>')
    c = sealed.counts(x)
    assert c == {"total": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1, "report": "ok"}
    assert "secret" not in repr(c)
    assert sealed.counts(tmp_path / "missing.xml")["errors"] == 1
    bomb = tmp_path / "b.xml"
    bomb.write_text('<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    assert sealed.counts(bomb)["report"] == "refused"


def test_passed_needs_a_test_and_no_failure():
    assert sealed.passed({"total": 2, "passed": 2, "failed": 0, "errors": 0})
    assert not sealed.passed({"total": 0, "passed": 0, "failed": 0, "errors": 0})
    assert not sealed.passed({"total": 2, "passed": 1, "failed": 1, "errors": 0})
    assert not sealed.passed({"total": 1, "passed": 1, "failed": 0, "errors": 0, "timed_out": True})


def test_run_has_a_clean_environment_and_keeps_output_off_stdout(tmp_path, capfd, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("KNOS_GATE_HIDDEN", "c2VjcmV0")
    work = tmp_path / "w"
    work.mkdir()
    (work / "test_env.py").write_text(
        "import os\n"
        "def test_no_secrets():\n"
        "    assert 'GH_TOKEN' not in os.environ and 'KNOS_GATE_HIDDEN' not in os.environ\n"
        "    print('THIS-OUTPUT-STAYS-IN-THE-LOG')\n")
    c = sealed.run(f"{sys.executable} -m pytest -q -s test_env.py", work, tmp_path / "j" / "r.xml", tmp_path / "log.txt", sandbox="none")
    assert c["passed"] == 1 and c["total"] == 1 and c["sandbox"] == "none"
    assert "THIS-OUTPUT-STAYS-IN-THE-LOG" not in capfd.readouterr().out
    assert "THIS-OUTPUT-STAYS-IN-THE-LOG" in (tmp_path / "log.txt").read_text()


def test_a_non_pytest_command_counts_by_exit_code(tmp_path):
    c = sealed.run(f"{sys.executable} -c \"raise SystemExit(3)\"", tmp_path, tmp_path / "j" / "r.xml", tmp_path / "l", sandbox="none")
    assert c["failed"] == 1 and c["exit"] == 3


def test_leaks_finds_hidden_lines(tmp_path):
    f = tmp_path / "test_h.py"
    f.write_text("def test_x():\n    assert compute(41) == 'the-answer-is-42'\nx=1\n")
    lines = sealed.hidden_lines([f])
    assert "x=1" not in lines
    assert sealed.leaks("all good", lines) == []
    assert sealed.leaks("oops assert compute(41) == 'the-answer-is-42' here", lines)


# ---- review fixes: blocker 1 (no write through a sandbox-made link), blocker 2 (fail closed), major 12 (exit code) ----

def test_the_log_is_a_new_file_and_a_planted_link_is_not_followed(tmp_path):
    target = tmp_path / "knos_module.py"
    target.write_text("ORIGINAL\n")
    log = tmp_path / "public.log"
    log.symlink_to(target)
    work = tmp_path / "w"
    work.mkdir()
    sealed.run(f"{sys.executable} -c \"print('OVERWRITE')\"", work, None, log, sandbox="none")
    assert target.read_text() == "ORIGINAL\n" and not log.is_symlink() and "OVERWRITE" in log.read_text()


def test_the_report_is_read_from_a_fresh_box_that_is_removed(tmp_path, monkeypatch):
    import tempfile
    made = []
    real = tempfile.mkdtemp
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])
    work = tmp_path / "w"
    work.mkdir()
    (work / "test_ok.py").write_text("def test_ok():\n    pass\n")
    c = sealed.run(f"{sys.executable} -m pytest -q test_ok.py", work, None, tmp_path / "log", sandbox="none")
    assert c["passed"] == 1 and len(made) == 1 and Path(made[0]).name.startswith("knos-gate-box-") and not Path(made[0]).exists()


def test_a_report_that_is_a_link_is_not_read(tmp_path):
    real = tmp_path / "real.xml"
    real.write_text('<testsuite><testcase name="a"/></testsuite>')
    link = tmp_path / "link.xml"
    link.symlink_to(real)
    assert sealed.counts(real)["passed"] == 1
    assert sealed.counts_bytes(sealed._read_report(link))["report"] == "missing"


def test_a_pass_needs_exit_code_zero(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    (work / "test_ok.py").write_text("import atexit, os\n\ndef test_ok():\n    atexit.register(lambda: os._exit(3))\n")
    c = sealed.run(f"{sys.executable} -m pytest -q test_ok.py", work, None, tmp_path / "log", sandbox="none")
    assert c["passed"] == 1 and c["exit"] == 3 and not sealed.passed(c)


def test_the_actions_sandbox_fails_closed_without_its_user(monkeypatch):
    monkeypatch.delenv("KNOS_GATE_SANDBOX_USER", raising=False)
    with pytest.raises(sealed.Refused, match="does not run"):
        sealed.sandbox_prefix("nonet,user")
    with pytest.raises(sealed.Refused, match="unknown sandbox"):
        sealed.sandbox_prefix("whatever")


def test_the_action_requires_the_sandbox():
    text = (Path(__file__).resolve().parents[1] / "actions" / "gate" / "action.yml").read_text()
    assert 'inputs.sandbox }}" != "nonet,user"' in text and "exit 2" in text and "default: nonet,user" in text
    assert "core.quotePath=false" in text
