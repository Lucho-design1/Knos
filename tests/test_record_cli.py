"""`knos record verify|anchor|journal|prove` reach Knos Record; `knos record verify <answer>.json` still reaches the
paid-answer verifier (tests/test_record_answer.py)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from knos import record
from knos.cli import app


def _fill(rec):
    record.claim("c1", {"title": "synthetic", "synthetic": True}, root=rec)
    record.append("verdict", {"passed": True, "synthetic": True}, claim="c1", root=rec)


def test_verify_journal_and_dry_run_anchor_through_knos_record(tmp_path):
    rec = tmp_path / "rec"
    _fill(rec)
    run = CliRunner()
    got = run.invoke(app, ["record", "verify", str(rec), "--offline"])
    assert got.exit_code == 0, got.output
    assert "2 line(s)" in got.output and got.output.strip().endswith("OK")
    got = run.invoke(app, ["record", "verify", str(rec / "journal.jsonl"), "--offline", "--json"])
    assert got.exit_code == 0 and json.loads(got.output)["lines"] == 2
    got = run.invoke(app, ["record", "journal", str(rec)])
    assert got.exit_code == 0 and "verdict" in got.output and "WARM" in got.output
    got = run.invoke(app, ["record", "anchor", str(rec), "--dry-run"])
    assert got.exit_code == 0 and "Would anchor seq 0..1" in got.output
    assert len(record.entries(rec)) == 2                                         # a dry run writes nothing


def test_a_broken_record_exits_one_and_says_why(tmp_path):
    rec = tmp_path / "rec"
    _fill(rec)
    text = (rec / "journal.jsonl").read_text(encoding="utf-8").replace('"passed":true', '"passed":false')
    (rec / "journal.jsonl").write_text(text, encoding="utf-8")
    got = CliRunner().invoke(app, ["record", "verify", str(rec), "--offline", "--no-sibyl"])
    assert got.exit_code == 1 and "does not hash to what it says" in got.output


def test_anchor_without_a_wallet_says_how(tmp_path):
    rec = tmp_path / "rec"
    _fill(rec)
    got = CliRunner().invoke(app, ["record", "anchor", str(rec)])
    assert got.exit_code == 2


def test_a_bare_verb_is_still_a_github_login(monkeypatch):
    """Review finding 36: `knos record anchor` with nothing after it is the record of the GitHub login "anchor", as it
    was before Knos Record; the Record's verbs need a folder, a seq or an option after them."""
    import importlib
    called = []
    record_cli = importlib.import_module("knos.record.cli")
    monkeypatch.setattr(record_cli, "main", lambda argv: called.append(argv) or 0)
    from knos import cli
    monkeypatch.setattr(cli, "_github", lambda path: (_ for _ in ()).throw(cli.Stop(f"looked up {path}")))
    got = CliRunner().invoke(app, ["record", "journal"])
    assert called == [] and "users/journal" in (got.output + str(got.exception))      # the login was looked up
    assert CliRunner().invoke(app, ["record", "journal", "somewhere"]).exit_code == 0 and called == [["journal", "somewhere"]]
