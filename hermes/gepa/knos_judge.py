"""The Knos referee as the judge for Hermes self-evolution (GEPA): a DSPy metric that scores a candidate by running it
against a sealed task, not by asking a model whether it looks right.

Hermes self-evolution (NousResearch/hermes-agent-self-evolution, evolution/core/fitness.py) passes a metric to
`dspy.GEPA(metric=...)`; its own metric is `skill_fitness_metric(example, prediction, trace=None) -> float` and reads
`prediction.output`. This module offers a drop-in with the same call shape (plus the two extra arguments DSPy's GEPA
passes, `pred_name` and `pred_trace`):

    from hermes.gepa.knos_judge import knos_metric          # or make_metric(tasks_dir=...)
    optimizer = dspy.GEPA(metric=knos_metric, ...)

Each example names a sealed task (`example.knos_task`: a task folder, see knos.verify.sealed) and the candidate's
answer (`prediction.output`) must contain a unified diff. The diff is applied to a copy of the task's base and judged
by the referee (knos.referee.judge_candidate: hidden tests sealed before the work, the locked judge hash, the cheat
library, a re-run). A task without a seal, or an install without the referee, scores 0.0 unless the caller passes
`allow_unsealed=True`, which uses a labelled fallback that the candidate's own code can forge: demos only.

Score: 1.0 when the sealed checks pass, 0.0 otherwise. A cheat (edited tests, out-of-scope files, data tampering, ...)
scores 0.0, never more than an honest failure, and its category is named in the feedback, so evolution cannot climb
by gaming the check: the only way up is to pass tests the candidate never saw. `scale="raw"` returns the referee's
own reward instead (1.0 / 0.0 / -1.0). When DSPy is importable the metric returns `dspy.Prediction(score=...,
feedback=...)`, which GEPA's reflection reads; otherwise a float.

Devnet/demo only: nothing here moves money. The example tasks under hermes/atropos/tasks/ are synthetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "knos").is_dir() and str(_SRC) not in sys.path:      # run from a Knos checkout without installing it
    sys.path.insert(0, str(_SRC))

from knos.verify import sealed  # noqa: E402


def _score(reward: float, scale: str) -> float:
    return float(reward) if scale == "raw" else (1.0 if reward >= 1.0 else 0.0)


def make_metric(tasks_dir: str | Path | None = None, scale: str = "unit", referee=None, with_feedback: bool | None = None,
                allow_unsealed: bool = False):
    """A GEPA metric. Without the referee and a task's seal every answer scores 0.0 ("unsealed"); `allow_unsealed`
    scores with the forgeable fallback instead (a demo on the synthetic tasks, never real evolution). `tasks_dir`: where `example.knos_task` names are looked up when they are not paths. `referee`:
    a module with judge_candidate (tests give one; default knos.referee, else the fallback)."""
    cache: dict[str, sealed.Task] = {}

    def task_of(example) -> sealed.Task:
        name = str(getattr(example, "knos_task", "") or (example.get("knos_task") if isinstance(example, dict) else ""))
        if not name:
            raise ValueError("the example names no sealed task (knos_task)")
        if name not in cache:
            path = Path(name)
            if not path.is_dir() and tasks_dir is not None:
                path = Path(tasks_dir) / name
            cache[name] = sealed.load_task(path)
        return cache[name]

    def metric(example, prediction, trace=None, pred_name=None, pred_trace=None):
        output = getattr(prediction, "output", None)
        if output is None and isinstance(prediction, dict):
            output = prediction.get("output")
        result = sealed.judge(task_of(example), str(output or ""), referee=referee, allow_unsealed=allow_unsealed)
        score = _score(result["reward"], scale)
        want = with_feedback
        if want is None:
            want = "dspy" in sys.modules
        if want:
            try:
                import dspy  # type: ignore[import-not-found]
                return dspy.Prediction(score=score, feedback=sealed.feedback(result))
            except ImportError:
                pass
        return score

    metric.__name__ = "knos_metric"
    return metric


knos_metric = make_metric()
