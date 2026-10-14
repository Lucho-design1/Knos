"""knos self: the line between the trusted core and the product, enforced (targets.yml + CODEOWNERS), and the merge
rules that read a change without running it."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from knos import cheats
from knos.self import cli, config, rules

ROOT = Path(__file__).resolve().parents[1]


def _diff(path: str, removed=(), added=(), status="modified") -> str:
    head = f"diff --git a/{path} b/{path}\n"
    if status == "removed":
        head += "deleted file mode 100644\n"
    head += f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n"
    return head + "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)


def test_targets_yml_is_valid_and_keeps_the_founders_switches_off():
    cfg = config.load(ROOT)
    assert cfg["loop"]["auto_merge_to_main"] is False                    # the founder switches auto-merge on, by hand
    assert tuple(cfg["loop"]["rollout"]) == ("sealed", "shadow", "canary", "main")
    assert cfg["loop"]["daily_merge_cap"] >= 0 and cfg["loop"]["network"] == "devnet"
    open_ = [t for t in cfg["targets"] if t["status"] == "open"]
    assert open_ and all(t["kind"] == "product" for t in open_)
    assert {t["kind"] for t in cfg["targets"]} == {"product", "referee"}


def test_codeowners_and_targets_core_are_the_same_list():
    cfg = config.load(ROOT)
    owned = config.codeowners_core(ROOT, cfg["founder"])
    assert set(owned) == set(cfg["core"])
    assert set(config.codeowners_core(ROOT)) == set(owned)              # the founder owns every listed path


@pytest.mark.parametrize("path, kind", [
    ("src/knos/referee/works.py", "core"), ("src/knos/cheats/rules.py", "core"), ("src/knos/judge.py", "core"),
    ("src/knos/gate/sealed.py", "core"), ("programs-v2/knos_pay/src/lib.rs", "core"), (".github/workflows/tests.yml", "core"),
    ("config/fees.yaml", "core"), ("targets.yml", "core"), ("CODEOWNERS", "core"), ("uv.lock", "core"),
    ("crates/knos-pay-interface/Cargo.lock", "core"), ("src/knos/self/loop.py", "core"), ("tests/bench_tamper/attacks.py", "core"),
    ("src/knos/mcp.py", "product"), ("docs/reference/SELF.md", "product"), ("web/app.js", "product"), ("tests/test_mcp.py", "product"),
    ("random/elsewhere.txt", "outside")])
def test_every_path_is_core_product_or_outside(path, kind):
    assert config.classify(path, config.load(ROOT)) == kind


def test_an_agent_pr_that_touches_a_core_path_is_refused(tmp_path):
    d = tmp_path / "pr.diff"
    d.write_text(_diff("src/knos/cheats/library.py", ["    return any(f.severity == 'refuse' for f in findings)"], ["    return False"]))
    assert cli.main(["check-pr", str(d), "--root", str(ROOT)]) == 1
    d.write_text(_diff("src/knos/mcp.py", ["import urllib.request"], ["import urllib.parse"]))
    assert cli.main(["check-pr", str(d), "--root", str(ROOT), "--target", "mcp-cold-start"]) == 0


def test_a_pr_that_deletes_a_test_or_a_detector_marker_or_logging_is_flagged_and_refused(tmp_path):
    cfg = config.load(ROOT)
    gone = _diff("tests/test_mcp.py", ["def test_x():", "    assert f() == 1"], status="removed")
    found = cheats.scan_diff(gone, core=tuple(config.core_globs(cfg)))
    assert cheats.refused(found) and "test_edited" in cheats.categories(found)
    marker = _diff("src/knos/mcp.py", ["x = 1  # knos:detector input-check"], ["x = 1"])
    found = cheats.scan_diff(marker)
    assert any(f.rule == "detector_marker_removed" for f in found) and cheats.refused(found)
    p, c = tmp_path / "p", tmp_path / "c"
    for d in (p, c):
        (d / "src").mkdir(parents=True)
    log = _diff("src/knos/mcp.py", ['    print(f"knos mcp: {name}", file=sys.stderr)'], [])
    found, _ = rules.static_findings(log, p, c)
    assert [f.rule for f in found] == ["self.logging_removed"] and found[0].severity == "refuse"


def test_fewer_tests_or_asserts_in_the_changed_files_are_refused(tmp_path):
    p, c = tmp_path / "p", tmp_path / "c"
    (p / "tests").mkdir(parents=True)
    (c / "tests").mkdir(parents=True)
    (p / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n    assert 2 == 2\n\ndef test_b():\n    assert 3\n")
    (c / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
    d = _diff("tests/test_a.py", ["def test_b():"], [])
    found, counts = rules.static_findings(d, p, c)
    assert counts == {"tests_before": 2, "tests_after": 1, "asserts_before": 3, "asserts_after": 1}
    assert {f.rule for f in found} == {"self.test_count_dropped", "self.asserts_dropped"}
    assert rules.proposed_rules(found) == ["self.asserts_dropped", "self.test_count_dropped"]


def test_targets_yml_refuses_a_target_that_opens_the_core_or_turns_on_auto_merge():
    good = config.load(ROOT)
    for change, words in (
            (lambda d: d["targets"][0]["scope"].append("src/knos/referee/works.py"), "trusted core"),
            (lambda d: d["loop"].__setitem__("auto_merge_to_main", True), "auto_merge_to_main"),
            (lambda d: d["loop"].__setitem__("network", "mainnet"), "devnet"),
            (lambda d: d["loop"].__setitem__("rollout", ["sealed", "main"]), "rollout"),
            (lambda d: d["core"].remove("src/knos/cheats/**"), "src/knos/cheats/**"),
            (lambda d: d["targets"][0].__setitem__("bounty_usd", "50.00"), "canary_bounty_max_usd")):
        doc = copy.deepcopy({k: v for k, v in good.items() if k != "_root"})
        change(doc)
        assert any(words in p for p in config.validate(doc)), words


def test_codeowners_patterns_become_globs():
    text = "# c\n/src/knos/referee/ @drexthealpha\n/action.yml @drexthealpha\n*.lock @drexthealpha\ndocs/ @someone\n"
    assert config.codeowners_globs(text) == ["src/knos/referee/**", "action.yml", "*.lock", "**/docs/**"]
    assert config.codeowners_globs(text, "drexthealpha") == ["src/knos/referee/**", "action.yml", "*.lock"]


def test_the_implausible_gain_check_fails_closed():
    assert rules.implausible(97, 60, 0.6) is True and rules.implausible(97, 29, 0.6) is False
    assert rules.implausible(97, 5, None) is True                  # no limit set: held for the founder
    assert rules.implausible(0, 5, 0.6) is True                    # a gain on a zero parent: held
    assert rules.implausible(97, 0, 0.6) is False


def test_the_jail_masks_the_state_the_wallets_and_the_other_tree(monkeypatch, tmp_path):
    from knos.self import tiers
    monkeypatch.setattr(tiers, "jail_available", lambda: True)
    tiers.configure(mask=[tmp_path / "state" / "referee-main", tmp_path / "wallets"], ro=[tmp_path / "repo" / ".git"],
                    trees=[tmp_path / "parent", tmp_path / "cand"])
    argv, kind = tiers._prefix({"PATH": "/usr/bin"}, "auto", tmp_path / "cand")
    script = argv[argv.index("-c") + 1]
    assert argv[:5] == ["sudo", "-n", "unshare", "--net", "--mount"] and kind.startswith("nonet,mount")
    for masked in ("state/referee-main", "wallets", "parent"):
        assert f"knos-self-mask {tmp_path / masked}" in script
    assert f"knos-self-mask {tmp_path / 'cand'}" not in script            # the tree under test stays visible
    assert "remount,bind,ro" in script and "env -i" in script
    monkeypatch.setattr(tiers, "jail_available", lambda: False)
    with pytest.raises(tiers.NoSandbox):
        tiers._prefix({}, "auto", tmp_path / "cand")
    assert tiers._prefix({}, "none", tmp_path / "cand") == ([], "none")
