"""The autoresearch referee: sealing, each cheat rule on its known-bad case, re-run tolerance, the time budget, and
the sandbox never holding a hidden label. SYNTHETIC data throughout."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knos.autoresearch import judge, loop, proposers, sandbox, synth, task
from test_autoresearch_loop import EXAMPLE, small_task

BASE = (EXAMPLE / "train.py").read_text(encoding="utf-8")
GOOD = proposers.write_config(BASE, dict(proposers.read_config(BASE), features="square+pairs"))


@pytest.fixture()
def ref(tmp_path):
    return judge.LocalJudge(task.load(small_task(tmp_path)))


def test_the_sealed_file_must_match_the_committed_hash(tmp_path):
    root = small_task(tmp_path)
    task.load(root)
    (root / "referee" / "sealed.json").write_text('{"seed": "another"}\n', encoding="utf-8")
    with pytest.raises(task.TaskError, match="spec_tampering"):
        task.load(root)


def test_task_json_is_checked(tmp_path):
    root = small_task(tmp_path, seeds=[1])
    with pytest.raises(task.TaskError, match="two distinct seeds"):
        task.load(root)
    root2 = small_task(tmp_path / "b", editable="../train.py")
    with pytest.raises(task.TaskError, match="editable"):
        task.load(root2)


def test_the_spec_hash_moves_with_the_program_and_the_judge(tmp_path):
    t = task.load(small_task(tmp_path))
    h = t.spec_hash("j1")
    assert h != t.spec_hash("j2")
    t.program += "\nchanged"
    assert h != t.spec_hash("j1")


def test_an_honest_improvement_passes_and_scores_on_both_seeds(ref):
    v = ref.judge({"train.py": GOOD}, BASE)
    assert v.passed and not v.cheats and len(v.scores) == 2 and v.score > 0.75
    assert "val_accuracy" in v.reported


@pytest.mark.parametrize("files, rule, category", [
    ({"train.py": GOOD, "conftest.py": "x = 1\n"}, "AR-SCOPE", "out_of_scope"),
    ({"train.py": BASE}, "AR-NOCHANGE", "no_change"),
    ({"train.py": GOOD.replace("import time", "import time\nimport socket")}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("import time", "import time\nimport os")}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    __import__('subprocess')", 1)}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    data = open('labels.csv').read()", 1)}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    path = '../referee/sealed.json'", 1)}, "AR-SEALED", "data_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    path = '/tmp/hidden_final.csv'", 1)}, "AR-SEALED", "data_tampering"),
    ({"train.py": GOOD.replace("import time", "import time\nimport sys")}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("import time", "import time\nimport statistics").replace(
        "def main():", "def main():\n    statistics.sys.modules['o' + 's'].system('id')", 1)}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    random._os.listdir('.')", 1)}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    getattr(json, 'lo' + 'ads')", 1)}, "AR-IMPORT", "runner_tampering"),
    ({"train.py": GOOD.replace("def main():", "def main():\n    b = __builtins__", 1)}, "AR-IMPORT", "runner_tampering"),
])
def test_each_cheat_rule_refuses_its_known_bad_case_without_running_it(ref, files, rule, category):
    v = ref.judge(files, BASE)
    assert not v.passed and v.refused and v.scores == []
    assert (rule, category) in {(c.rule, c.category) for c in v.cheats}


def test_words_in_a_docstring_are_not_a_cheat(ref):
    src = GOOD.replace('"""The ONE file', '"""Scored on hidden, sealed data. The ONE file', 1)
    assert ref.judge({"train.py": src}, BASE).passed


def test_a_rerun_that_disagrees_is_refused(ref):
    flaky = GOOD.replace("    a = ap.parse_args()\n", "    a = ap.parse_args()\n    if a.seed == 2:\n        CONFIG['features'] = 'linear'\n", 1)
    v = ref.judge({"train.py": flaky}, BASE)
    assert not v.passed and [c.category for c in v.cheats] == ["rerun_mismatch"]


def test_overrunning_the_time_budget_fails_without_being_called_a_cheat(tmp_path):
    ref = judge.LocalJudge(task.load(small_task(tmp_path, time_budget_s=1)))
    slow = GOOD.replace("    a = ap.parse_args()\n", "    a = ap.parse_args()\n    time.sleep(30)\n", 1)
    v = ref.judge({"train.py": slow}, BASE)
    assert not v.passed and not v.refused and "time budget" in v.reasons[0]


def test_a_crash_or_bad_output_fails(ref):
    assert not ref.judge({"train.py": GOOD.replace("def main():", "def main():\n    raise SystemExit(3)", 1)}, BASE).passed
    bad = GOOD.replace('json.dump({"predictions": predict(model, Xp, CONFIG)}, f)', 'json.dump({"predictions": [2]}, f)')
    v = ref.judge({"train.py": bad}, BASE)
    assert not v.passed and "each 0 or 1" in v.reasons[0]


def test_the_sandbox_holds_features_but_never_the_hidden_labels():
    probe = (
        "import csv, json, sys\n"
        "head = next(csv.reader(open(sys.argv[sys.argv.index('--predict') + 1])))\n"
        "train = next(csv.reader(open(sys.argv[sys.argv.index('--train') + 1])))\n"
        "n = sum(1 for _ in open(sys.argv[sys.argv.index('--predict') + 1])) - 1\n"
        "if head[-1] == 'y' or train[-1] != 'y':\n    raise SystemExit(7)\n"
        "json.dump({'predictions': [0] * n}, open(sys.argv[sys.argv.index('--out') + 1], 'w'))\n")
    rows = synth.rows("t", 30)
    r = sandbox.run(probe, "train.py", {"train": rows, "val": rows}, rows, seed=1, budget_s=10)
    assert r.ok and r.predictions == [0] * 30


def test_graduation_refuses_when_the_judging_code_moved(tmp_path, knos_home, monkeypatch):
    t = task.load(small_task(tmp_path))
    ref = judge.LocalJudge(t)
    monkeypatch.setattr(judge, "judge_hash", lambda: "0" * 64)
    f = ref.final(t.baseline, GOOD)
    assert not f["graduated"] and not f["judge_unchanged"] and any("judge_drift" in r for r in f["reasons"])


def test_graduation_needs_the_lift_on_the_sealed_final_set(tmp_path):
    t = task.load(small_task(tmp_path, min_lift=0.9))
    f = judge.LocalJudge(t).final(t.baseline, GOOD)
    assert not f["graduated"] and any("below the agreed" in r for r in f["reasons"])


def test_with_knos_record_installed_the_loop_writes_through_it(tmp_path, knos_home):
    record = pytest.importorskip("knos.record")
    if not hasattr(record, "append"):
        pytest.skip("knos.record without the v0.3.29 API")
    t = task.load(small_task(tmp_path))
    rep = loop.run(t, proposers.LocalProposer(0), tmp_path / "o", 1, record_root=tmp_path / "rec", say=lambda *_: None)
    assert rep.record_backend == "knos.record"
    kinds = [e["kind"] for e in record.entries(root=tmp_path / "rec")]
    assert {"claim", "paper", "experiment", "verdict"} <= set(kinds)
    assert json.dumps(rep.record) and Path(tmp_path / "rec").exists()
