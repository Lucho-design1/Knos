"""Knos sealed tasks as an Atropos environment: a policy model trains against rewards the Knos referee computes from
tests it never saw. Devnet/demo only; the tasks in hermes/atropos/tasks/ are synthetic.

Interface (NousResearch/atropos, atroposlib/envs/base.py @296a0bc5): a BaseEnv subclass with a `name`, an
`env_config_cls`, `config_init()` (classmethod -> (config, server configs)), `setup()`, `get_next_item()` and
`evaluate()` (both abstract in BaseEnv), and `collect_trajectories(item) -> (ScoredDataGroup, backlog)`; run with
`python hermes/atropos/knos_env.py serve|process|evaluate ...` (BaseEnv.cli()).

Each item is one sealed task (knos.verify.sealed). The policy is shown only the task's prompt; it answers with a
unified diff; the diff is applied to a copy of the task's base and judged by knos.referee.judge_candidate (sealed
hidden tests, locked judge, cheat library, re-run). Tasks without a seal are refused at setup unless
`allow_unsealed` is set (the synthetic demo only: their fallback score can be forged). The score is the referee's reward:
1.0 passed, 0.0 failed or no usable patch, -1.0 a cheat refused, so reward hacking scores below an honest failure.

The pure parts (task loading, judging, the group's scores) are in knos.verify.sealed and in `score_group` below, and
are tested without atroposlib. The class is defined only when atroposlib is importable.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "knos").is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from knos.verify import sealed  # noqa: E402

TASKS = Path(__file__).resolve().parent / "tasks"
NAME = "knos_sealed"


def messages_for(task: sealed.Task) -> list[dict]:
    return [{"role": "system", "content": "You fix bugs in repositories. Answer with a unified diff only."},
            {"role": "user", "content": sealed.public_prompt(task)}]


def score_group(task: sealed.Task, answers: list[str], referee=None, allow_unsealed: bool = False) -> dict:
    """The referee's reward for each answer to one task: {"scores", "results"} (results carry reasons and cheat
    categories, never hidden test text)."""
    results = [sealed.judge(task, a, referee=referee, allow_unsealed=allow_unsealed) for a in answers]
    return {"scores": [float(r["reward"]) for r in results], "results": results}


try:
    from atroposlib.envs.base import APIServerConfig, BaseEnv, BaseEnvConfig, ScoredDataGroup  # type: ignore[import-not-found]
    from atroposlib.utils.tokenize_for_trainer import tokenize_for_trainer  # type: ignore[import-not-found]
    from pydantic import Field  # type: ignore[import-not-found]
except ImportError:          # atroposlib not installed: the pure parts above still work
    BaseEnv = None  # type: ignore[assignment,misc]


if BaseEnv is not None:

    class KnosEnvConfig(BaseEnvConfig):  # type: ignore[misc,valid-type]
        tasks_dir: str = Field(default=str(TASKS), description="folder of sealed tasks (each with task.json and base/)")
        eval_tasks_dir: str = Field(default="", description="sealed tasks for evaluate(); default: tasks_dir")
        allow_unsealed: bool = Field(default=False, description="score tasks without a seal with the forgeable fallback (the synthetic demo only)")

    class KnosSealedEnv(BaseEnv):  # type: ignore[misc,valid-type]
        name = NAME
        env_config_cls = KnosEnvConfig

        @classmethod
        def config_init(cls):
            model = os.environ.get("KNOS_ATROPOS_MODEL", "NousResearch/DeepHermes-3-Llama-3-3B-Preview")
            env = KnosEnvConfig(tokenizer_name=model, group_size=4, use_wandb=False, total_steps=100, batch_size=8,
                                steps_per_eval=50, max_token_length=4096, wandb_name=NAME)
            server = APIServerConfig(model_name=model, base_url=os.environ.get("KNOS_ATROPOS_BASE_URL", "http://localhost:9001/v1"),
                                     api_key=os.environ.get("KNOS_ATROPOS_API_KEY", "x"), num_requests_for_eval=32)
            return env, [server]

        async def setup(self):
            self.tasks = sealed.load_tasks(Path(self.config.tasks_dir))
            self.eval_tasks = sealed.load_tasks(Path(self.config.eval_tasks_dir)) if self.config.eval_tasks_dir else self.tasks
            if not self.tasks:
                raise RuntimeError(f"no sealed tasks in {self.config.tasks_dir}")
            unsealed = [t["id"] for t in [*self.tasks, *self.eval_tasks] if not t.get("seal")]
            if unsealed and not self.config.allow_unsealed:
                raise RuntimeError(f"tasks without a seal: {', '.join(unsealed)}. Their reward could be forged by the policy's own "
                                   "code; seal them with knos.referee, or set allow_unsealed only for the synthetic demo")
            self.iter = 0
            self.last_eval: dict = {}

        async def get_next_item(self):
            task = self.tasks[self.iter % len(self.tasks)]
            self.iter += 1
            return task

        async def collect_trajectories(self, item):
            msgs = messages_for(item)
            got = await self.server.chat_completion(messages=msgs, n=self.config.group_size,
                                                    max_tokens=self.config.max_token_length, temperature=1.0)
            answers = [c.message.content or "" for c in got.choices]
            scored = await asyncio.to_thread(score_group, item, answers, None, self.config.allow_unsealed)
            group = ScoredDataGroup()
            group["tokens"], group["masks"], group["scores"], group["messages"] = [], [], [], []
            for answer, score in zip(answers, scored["scores"]):
                chat = [*msgs, {"role": "assistant", "content": answer}]
                out = tokenize_for_trainer(self.tokenizer, chat)
                group["tokens"].append(out["tokens"])
                group["masks"].append(out["masks"])
                group["scores"].append(score)
                group["messages"].append(chat)
            return group, []

        async def evaluate(self, *args, **kwargs):
            passed = total = 0
            for task in self.eval_tasks:
                got = await self.server.chat_completion(messages=messages_for(task), n=1,
                                                        max_tokens=self.config.max_token_length, temperature=0.0, split="eval")
                result = await asyncio.to_thread(sealed.judge, task, got.choices[0].message.content or "", None, self.config.allow_unsealed)
                passed += int(bool(result["passed"]))
                total += 1
            self.last_eval = {"eval/knos_pass_rate": passed / total if total else 0.0}

        async def wandb_log(self, wandb_metrics=None):
            metrics = dict(wandb_metrics or {})
            metrics.update(getattr(self, "last_eval", {}) or {})
            await super().wandb_log(metrics)


if __name__ == "__main__":
    if BaseEnv is None:
        raise SystemExit("atroposlib is not installed: install NousResearch/atropos to serve this environment")
    KnosSealedEnv.cli()
