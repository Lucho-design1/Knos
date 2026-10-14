"""Works: sealed hidden tests, a locked judge, the cheat rules and the re-run, end to end on the tamper samples.

The sealed bundle is the sample's black-box bundle, moved OUT of the repository (the worker's tree never has it) and
sealed under another issue number before any work: what a funder does with Knos Gate's hidden suite."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from knos import cheats, referee

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tests" / "bench_tamper"
BLACKBOX = os.name != "nt"          # the black-box check reaches the tree through a shell wrapper (as the benchmark says)
FOLDER = {"python": "sample", "node": "sample_node", "ruby": "sample_ruby"}
NEEDS = {"python": (), "node": ("node",), "ruby": ("ruby",)}


def _sealed(tmp: Path, lang: str = "python") -> tuple[Path, dict]:
    hidden = tmp / "sealed"
    shutil.copytree(BENCH / FOLDER[lang] / ".knos" / "acceptance" / "2", hidden)
    return hidden, referee.seal(hidden, issue="9", test_dirs=["tests"] if lang == "python" else ["test"])


def _trees(tmp: Path, lang: str, build) -> tuple[Path, Path]:
    base, pr = tmp / "base", tmp / "pr"
    if isinstance(build, cheats.Case):
        cheats.build_case(build, base, pr)
    else:
        shutil.copytree(BENCH / FOLDER[lang], base)
        shutil.copytree(BENCH / FOLDER[lang], pr)
        build(pr)
    for root in (base, pr):                       # the hidden bundle is not in the repository
        shutil.rmtree(root / ".knos" / "acceptance" / "2", ignore_errors=True)
    return base, pr


def _control(lang: str):
    sys.path.insert(0, str(BENCH))
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"knos_works_{lang}", BENCH / {"python": "attacks.py", "node": "attacks_node.py",
                                                                                "ruby": "attacks_ruby.py"}[lang])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.control


def test_the_seal_names_the_bundle_and_the_judging_code(tmp_path):
    from knos import judge
    hidden, s = _sealed(tmp_path)
    assert s["spec_hash"] == judge.checks_hash(hidden) and s["judge_hash"] == referee.judge_hash()
    assert len(referee.seal_hash(s)) == 64 and referee.seal_hash(s) == referee.seal_hash(dict(s))
    assert referee.judge_hash() != referee.judge_hash(["judge.py"])        # the referee and cheat library are in it


def test_a_bundle_swapped_after_sealing_is_refused_before_anything_runs(tmp_path):
    hidden, s = _sealed(tmp_path)
    base, pr = _trees(tmp_path, "python", _control("python"))
    (hidden / "blackbox.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    ran = []
    c = referee.works(base, pr, s, hidden_dir=hidden, judge_fn=lambda *a, **k: ran.append(1))
    assert not c.passed and "sealed tests changed" in c.reasons[0] and not ran
    assert [f.category for f in c.cheats] == ["sealed_tests_changed"]


def test_a_referee_other_than_the_sealed_one_does_not_judge(tmp_path, monkeypatch):
    """A worker who edits the referee in its own pull request changes nothing: the running install's judging code must
    hash to what was sealed, and the PR's copy is never the one that runs."""
    hidden, s = _sealed(tmp_path)
    base, pr = _trees(tmp_path, "python", _control("python"))
    c = referee.works(base, pr, {**s, "judge_hash": "0" * 64}, hidden_dir=hidden, judge_fn=lambda *a, **k: 1 / 0)
    assert not c.passed and "locked judge" in c.reasons[0] and c.cheats[0].category == "judge_drift"
    # and a pull request that edits the referee is refused by the path rules when the referee is in scope of nothing
    (pr / "src" / "knos" / "referee").mkdir(parents=True)
    (pr / "src" / "knos" / "referee" / "works.py").write_text("def works(*a, **k):\n    return True\n", encoding="utf-8")
    c = referee.works(base, pr, s, hidden_dir=hidden, core=["src/knos/referee/**"], judge_fn=lambda *a, **k: 1 / 0)
    assert not c.passed and "core_path_touched" in {f.rule for f in c.cheats}


@pytest.mark.parametrize("case", [c for c in cheats.CASES if c.language == "python"][:6], ids=lambda c: c.id)
def test_cheat_rules_refuse_before_the_judge_runs(case, tmp_path):
    hidden, s = _sealed(tmp_path)
    base, pr = _trees(tmp_path, "python", case)
    c = referee.works(base, pr, s, hidden_dir=hidden, judge_fn=lambda *a, **k: pytest.fail("the judge ran"))
    assert not c.passed and case.expect <= {f.rule for f in c.cheats} and referee.reward(c) == -1.0


def _flip():
    calls = []

    def judge_fn(base, pr, cfg, **kw):
        calls.append(1)
        return {"passed": len(calls) == 1, "verdict": "accepted" if len(calls) == 1 else "rejected", "reasons": [],
                "checks_hash": None, "notes": []}
    return judge_fn


def test_a_rerun_that_disagrees_is_refused(tmp_path):
    hidden, s = _sealed(tmp_path)
    base, pr = _trees(tmp_path, "python", _control("python"))
    c = referee.works(base, pr, s, hidden_dir=hidden, judge_fn=_flip())
    assert not c.passed and "re-run disagrees" in c.reasons[0] and c.cheats[-1].category == "rerun_mismatch"


def test_a_metric_must_reproduce_within_the_agreed_tolerance(tmp_path):
    hidden, _ = _sealed(tmp_path)
    s = referee.seal(hidden, issue="9", test_dirs=["tests"], tolerance={"abs": 0.01, "rel": 0.0}, reruns=2)
    base, pr = _trees(tmp_path, "python", _control("python"))
    values = iter([0.900, 0.905, 0.95])

    def judge_fn(*a, **k):
        return {"passed": True, "verdict": "accepted", "reasons": [], "notes": [], "metric": next(values)}
    c = referee.works(base, pr, s, hidden_dir=hidden, judge_fn=judge_fn)
    assert not c.passed and "not within tolerance" in c.reasons[0] and len(c.evidence["reruns"]) == 2
    assert referee.within_tolerance(100, 101, rel_tol=0.01) and not referee.within_tolerance(100, 102, rel_tol=0.01)
    assert referee.rerun_agrees({"passed": True, "metric": 1.0}, {"passed": True, "metric": 1.0}) == (True, [])


@pytest.mark.skipif(not BLACKBOX, reason="the black-box check reaches the tree through a shell wrapper")
def test_the_honest_fix_passes_the_sealed_tests_twice(tmp_path):
    hidden, s = _sealed(tmp_path)
    base, pr = _trees(tmp_path, "python", _control("python"))
    c = referee.works(base, pr, s, hidden_dir=hidden)
    assert c.passed, c.reasons
    assert c.evidence["verdict"]["assurance"] in ("black-box", "hermetic") and c.evidence["reruns"][0]["agree"]
    assert referee.reward(c) == 1.0


def _end_to_end():
    out = []
    for c in cheats.CASES:
        if c.bench[1] in cheats.JUDGED_END_TO_END:
            out.append(pytest.param(c, id=c.id, marks=pytest.mark.skipif(
                not BLACKBOX or not all(shutil.which(t) for t in NEEDS[c.language]), reason="needs the black-box runner and the language")))
    return out


@pytest.mark.parametrize("case", _end_to_end())
def test_what_no_text_rule_can_see_the_sealed_tests_refuse_on_their_own(case, tmp_path):
    """A no-op claim, constants for the visible examples, forgery from inside the test process: with the cheat rules
    switched OFF, the sealed black-box tests still refuse each (the rules and the tests are two independent walls)."""
    hidden, s = _sealed(tmp_path, case.language)
    base, pr = _trees(tmp_path, case.language, case)
    c = referee.works(base, pr, s, hidden_dir=hidden, scan=False, reruns=0)
    assert not c.passed and any(r.startswith("hidden tests: rejected") for r in c.reasons), c.reasons
    shown = referee.judge_candidate(base, pr, s, hidden_dir=hidden, scan=False, reruns=0)
    assert shown["reward"] == 0.0 and all("last words" not in r for r in shown["reasons"])       # the sealed suite's output is withheld


def test_works_writes_the_verification_and_every_cheat_to_the_record(tmp_path, monkeypatch):
    got = []
    fake = type(sys)("knos.record")
    fake.append = lambda kind, payload, **kw: got.append((kind, payload)) or {"kind": kind}
    monkeypatch.setitem(sys.modules, "knos.record", fake)
    import knos
    monkeypatch.setattr(knos, "record", fake, raising=False)
    hidden, s = _sealed(tmp_path)
    case = next(c for c in cheats.CASES if c.id == "python-02")
    base, pr = _trees(tmp_path, "python", case)
    c = referee.works(base, pr, s, hidden_dir=hidden, record=True, judge_fn=lambda *a, **k: pytest.fail("ran"))
    kinds = [k for k, _ in got]
    assert kinds[0] == "verification" and kinds.count("cheat") == len(c.cheats) >= 2 and c.evidence["recorded"] is True
    assert got[0][1]["passed"] is False and "test_edited" in got[0][1]["cheats"]
