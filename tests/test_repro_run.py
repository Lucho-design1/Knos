"""knos reproduce PATH: a small public-style ML repository (SYNTHETIC data) reproduces within tolerance and gets the
"Reproduced by Knos" badge; a tampered result is contested and kept private (tests/test_repro_privacy.py holds the
privacy rules in detail)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from knos.repro import example, publish as pb, run as rr, spec as sp


def _spec(root):
    """The example's spec with a budget wide enough for a loaded test machine (the budget itself is tested below)."""
    spec, sha = sp.load(root)
    spec["compute"]["max_seconds"] = 900.0
    return spec, sha


def test_the_honest_example_reproduces_on_the_rerun_and_the_held_out_split(tmp_path):
    root = example.write(tmp_path / "ex", python=sys.executable)
    spec, sha = _spec(root)
    result, logs = rr.reproduce(root, spec, sha, seed_source=lambda: 12345, version="test")
    c = result["claims"][0]
    assert result["status"] == "reproduced" and result["private"] is False and not result["cheats"]
    assert c["rerun"] == example.HONEST            # the measured number the example states, held here
    assert abs(c["heldout"] - example.HONEST) <= 0.07 and c["holds"]
    assert result["heldout"]["source"].startswith("generator") and result["heldout"]["seed_sha256"] and "12345" not in json.dumps(result)
    assert result["digest"] == rr.digest(result) and pb.checks(result) == ""
    svg = pb.badge_svg(result)
    assert "Reproduced by Knos" in svg and "1/1 claim" in svg and "<script" not in svg


def test_a_tampered_result_is_contested_and_never_gets_a_badge(tmp_path):
    root = example.write(tmp_path / "ex", tamper=True, python=sys.executable)
    spec, sha = _spec(root)
    result, _ = rr.reproduce(root, spec, sha, seed_source=lambda: 12345)
    assert result["status"] == "contested" and result["private"] is True and result["funding"] is None
    assert "outside" in result["claims"][0]["why"] and not result["claims"][0]["holds"]
    with pytest.raises(pb.NotPublishable):
        pb.badge_svg(result)


def test_a_results_file_that_disagrees_with_knos_yml_fires_reported_mismatch(tmp_path):
    root = example.write(tmp_path / "ex", python=sys.executable)
    (root / "results.json").write_text('{"accuracy": 0.99}', encoding="utf-8")       # the README's number inflated, the spec honest
    spec, sha = _spec(root)
    result, _ = rr.reproduce(root, spec, sha, seed_source=lambda: 3)
    assert result["status"] == "contested" and [c["rule"] for c in result["cheats"]] == ["reported_mismatch"]


def test_an_entry_that_edits_protected_data_fires_data_tamper(tmp_path):
    root = example.write(tmp_path / "ex", python=sys.executable)
    train = root / "train.py"
    train.write_text(train.read_text() + "\nopen('results.json', 'w').write('{\"accuracy\": %s}' % acc)\n", encoding="utf-8")
    spec, sha = _spec(root)
    result, _ = rr.reproduce(root, spec, sha, seed_source=lambda: 3)
    assert result["status"] == "contested" and {c["rule"] for c in result["cheats"]} >= {"data_tamper"}
    assert (root / "results.json").read_text().strip() == '{"accuracy": %s}' % example.HONEST      # the authors' copy is never touched


def test_failed_incomplete_and_metric_missing(tmp_path):
    root = example.write(tmp_path / "ex", python=sys.executable)
    spec, sha = _spec(root)
    broken = dict(spec, entry=[sys.executable, "-c", "raise SystemExit(3)"])
    assert rr.reproduce(root, broken, sha, seed_source=lambda: 3)[0]["status"] == "failed"
    silent = dict(spec, entry=[sys.executable, "-c", "import json,os; json.dump({'other': 1}, open(os.environ['KNOS_METRICS_OUT'], 'w'))"])
    got = rr.reproduce(root, silent, sha, seed_source=lambda: 3)[0]
    assert got["status"] == "contested" and {c["rule"] for c in got["cheats"]} == {"metric_missing"}
    no_heldout = dict(spec, data=dict(spec["data"], generator=None, path="d"))
    (root / "d").mkdir()
    subprocess.run([sys.executable, "make_data.py", "--seed", "7", "--out", "d"], cwd=root, check=True)
    got = rr.reproduce(root, no_heldout, sha)[0]
    assert got["status"] == "incomplete" and got["private"] is True


def test_a_given_held_out_folder_is_used_and_the_budget_is_enforced(tmp_path):
    root = example.write(tmp_path / "ex", python=sys.executable)
    held = tmp_path / "sealed"
    subprocess.run([sys.executable, str(root / "make_data.py"), "--seed", "424242", "--out", str(held)], check=True)
    spec, sha = _spec(root)
    got = rr.reproduce(root, spec, sha, heldout=held)[0]
    assert got["heldout"]["source"] == "folder given at run time" and got["status"] == "reproduced"
    slow = dict(spec, entry=[sys.executable, "-c", "import time; time.sleep(5)"], compute={"max_seconds": 0.5, "cpu_only": True})
    got = rr.reproduce(root, slow, sha, seed_source=lambda: 3)[0]
    assert got["status"] == "failed" and "budget" in got["runs"][0]["why"]


def test_the_run_environment_carries_no_secret():
    env = rr.clean_env({"PATH": "/bin", "GH_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "y", "MY_API_KEY": "z", "KNOS_FEE_PAYER": "w", "HOME": "/h"}, seed=4)
    assert set(env) == {"PATH", "HOME", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "KNOS_REPRO"} and env["PYTHONHASHSEED"] == "4"


def test_the_command_line_reproduces_and_publishes(tmp_path):
    from typer.testing import CliRunner

    from knos import cli
    root = example.write(tmp_path / "ex", python=sys.executable)
    out = tmp_path / "out"
    got = CliRunner().invoke(cli.app, ["reproduce", str(root), "--out", str(out)])
    assert got.exit_code == 0, got.output
    assert "REPRODUCED" in got.output and (out / "public" / "synthetic-centroid" / "badge.svg").is_file()
    assert CliRunner().invoke(cli.app, ["reproduce", str(tmp_path / "nothing")]).exit_code == 2
