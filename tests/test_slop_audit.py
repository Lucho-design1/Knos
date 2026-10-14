"""The slop audit (research/slop_audit): its rules on known cases, its table on the committed SYNTHETIC fixture, and the
published table: reproducible from the committed output, and every number docs/reference/SLOP_AUDIT.md prints is in it.

The dataset itself is not needed here (and not in the repository): the fixture holds eight made-up pull requests in the
shape of AIDev rows, one per rule."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.slop_audit import __main__ as cli  # noqa: E402
from research.slop_audit import audit, rules  # noqa: E402

OUT = ROOT / "research" / "slop_audit" / "out"
DOC = ROOT / "docs" / "reference" / "SLOP_AUDIT.md"


@pytest.mark.parametrize("path,test", [
    ("tests/test_x.py", True), ("src/x_test.go", True), ("web/a.test.ts", True), ("a/__tests__/b.js", True),
    ("src/main/FooTest.java", True), ("spec/models/user_spec.rb", True), ("conftest.py", True),
    ("src/x.py", False), ("docs/testing.md", False), ("src/contest.py", False), ("latest/x.py", False)])
def test_a_test_file_is_known_by_its_directory_or_its_name(path, test):
    assert rules.is_test(path) is test


def test_ci_files_are_the_ci_configuration_files():
    assert rules.is_ci(".github/workflows/ci.yml") and rules.is_ci(".gitlab-ci.yml") and rules.is_ci("Jenkinsfile")
    assert not rules.is_ci("src/ci.py") and not rules.is_ci(".github/CODEOWNERS")


def test_a_commented_out_assertion_is_not_an_assertion_and_a_moved_skip_is_not_added():
    f = rules.file_signals("tests/test_a.py", "modified", "@@\n-# assert x\n+# assert y")
    assert f["asserts_removed"] == f["asserts_added"] == 0
    moved = rules.file_signals("tests/test_a.py", "modified", "@@\n-@pytest.mark.skip\n+@pytest.mark.skip")
    assert moved["skip_added"] is False


def test_claims_are_read_by_knos_own_reader_and_a_hedge_is_no_claim():
    assert rules.read_claims("All tests pass.")["tests_pass"]
    assert rules.read_claims("CI is green.")["ci_green"]
    assert not rules.read_claims("Tests should pass once CI runs.")["tests_pass"]
    assert not rules.read_claims("<!-- All tests pass -->")["tests_pass"]                 # an HTML comment claims nothing
    assert rules.read_claims("Added unit tests for the retry path.")["added_tests"]
    assert not rules.read_claims("I did not add tests.")["added_tests"]


def test_wilson_interval_has_known_values():
    assert audit.wilson(0, 0) is None
    assert audit.wilson(5, 10) == [0.2366, 0.7634]
    assert audit.wilson(0, 10)[0] == 0.0


def test_the_fixture_gives_the_table_worked_out_by_hand(tmp_path):
    assert cli.main(["fixture", "--out", str(tmp_path)]) == 0
    t = json.loads((tmp_path / "slop_audit.json").read_text())
    s = t["all"]
    assert (s["prs"], s["prs_with_file_list"], s["prs_merged"]) == (8, 7, 5)
    assert (s["touches_a_test_file"]["k"], s["touches_a_test_file"]["n"]) == (4, 7)
    assert (s["merged_without_a_test_file"]["k"], s["merged_without_a_test_file"]["n"]) == (2, 5)
    assert (s["modifies_an_existing_test_file"]["k"]) == 2
    assert (s["claims_tests_pass_or_ci_green"]["k"], s["claims_tests_pass_or_ci_green"]["n"]) == (2, 8)
    assert (s["false_claim_of_settled"]["k"], s["false_claim_of_settled"]["n"]) == (1, 2)
    assert (s["claims_tests_added_but_changes_no_test_file"]["k"], s["claims_tests_added_but_changes_no_test_file"]["n"]) == (1, 1)
    assert {k: v["k"] for k, v in s["cheat_rules"].items()} == {
        "test_deleted": 1, "asserts_removed": 1, "skip_added": 1, "ci_weakened": 1, "ci_test_cmd_removed": 1}
    assert (s["any_cheat_rule"]["k"], s["any_cheat_rule"]["n"]) == (4, 7)
    assert (s["fails_a_measured_knos_check"]["k"], s["fails_a_measured_knos_check"]["n"]) == (6, 7)
    assert (s["merged_although_failing_a_check"]["k"], s["merged_although_failing_a_check"]["n"]) == (4, 6)
    i = t["issue_linked"]
    assert (i["prs_linking_an_issue"], i["issues"], i["linked_prs_merged"]["k"]) == (3, 2, 1)
    assert (i["linked_prs_failing_a_measured_check"]["k"], i["linked_prs_failing_a_measured_check"]["n"]) == (2, 3)
    assert (i["issues_with_a_merged_and_an_unmerged_agent_pr"], i["of_those_merged_fix_changed_tests"],
            i["unmerged_attempts_judgeable_by_those_tests"]) == (1, 1, 1)
    assert sorted(t["by_agent"]) == ["AgentA", "AgentB"] and t["meta"]["dataset"] == "fixture (synthetic)"
    csv = (tmp_path / "slop_audit.csv").read_text().splitlines()
    assert csv[0].startswith("group,prs,") and [line.split(",")[0] for line in csv[1:]] == ["all", "AgentA", "AgentB"]


def test_the_fixture_run_is_reproducible(tmp_path):
    cli.main(["fixture", "--out", str(tmp_path / "a")])
    cli.main(["fixture", "--out", str(tmp_path / "b")])
    for name in ("slop_audit.json", "slop_audit.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def _published() -> dict:
    return json.loads((OUT / "slop_audit.json").read_text(encoding="utf-8"))


def test_the_published_table_is_consistent_and_its_csv_is_its_json():
    t = _published()
    assert t["meta"]["dataset_version"] == "v4" and t["meta"]["dataset_revision"]
    assert (OUT / "slop_audit.csv").read_text(encoding="utf-8") == audit.to_csv(t)
    for group in [t["all"], *t["by_agent"].values()]:
        for v in group.values():
            if isinstance(v, dict) and "k" in v:
                assert 0 <= v["k"] <= v["n"] and v["ci95"] == audit.wilson(v["k"], v["n"])
    assert t["all"]["prs"] == sum(g["prs"] for g in t["by_agent"].values())
    assert t["all"]["claimants_ci_read"] == sum(t["all"]["claimants_ci"].values())


def test_every_number_the_document_prints_is_in_the_published_table():
    """docs/reference/SLOP_AUDIT.md marks its measured numbers as `k/n` with a percentage; each pair is a k and n of
    one share in the table, and each percentage is that share, rounded as printed."""
    t = _published()
    pairs = set()

    def walk(v):
        if isinstance(v, dict):
            if "k" in v and "n" in v:
                pairs.add((v["k"], v["n"], v["share"]))
            for x in v.values():
                walk(x)
    walk(t)
    doc = DOC.read_text(encoding="utf-8")
    found = re.findall(r"\b([\d,]+) of ([\d,]+) \((\d+(?:\.\d)?)%\)", doc)
    assert len(found) >= 8, "the document prints its measured shares as 'k of n (p%)'"
    for k, n, pct in found:
        k, n = int(k.replace(",", "")), int(n.replace(",", ""))
        match = [s for kk, nn, s in pairs if (kk, nn) == (k, n)]
        assert match, f"{k} of {n} is not a share in the published table"
        assert any(abs(round(100 * s, len(pct.split(".")[1]) if "." in pct else 0) - float(pct)) < 1e-9 for s in match), (k, n, pct)
