"""Knos sealed tasks as an Atropos environment (hermes/atropos/knos_env.py). atroposlib is not a dependency, so its
interface is stood in for by a stub that holds exactly what knos_env uses of atroposlib/envs/base.py
(NousResearch/atropos@296a0bc5): BaseEnv with abstract get_next_item and evaluate, BaseEnvConfig (pydantic),
APIServerConfig, ScoredDataGroup (a TypedDict), and atroposlib.utils.tokenize_for_trainer."""

from __future__ import annotations

import abc
import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "hermes" / "atropos" / "tasks"
GOOD_ADD = "```diff\n--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n```\n"


def _load_env():
    sys.path.insert(0, str(ROOT / "hermes" / "atropos"))
    try:
        sys.modules.pop("knos_env", None)
        return importlib.import_module("knos_env")
    finally:
        sys.path.remove(str(ROOT / "hermes" / "atropos"))


def test_without_atroposlib_the_pure_parts_work_and_rewards_come_from_the_judge():
    env = _load_env()
    from knos.verify import sealed
    task = sealed.load_task(TASKS / "synthetic-add")
    got = env.score_group(task, [GOOD_ADD, "no idea", GOOD_ADD.replace("a + b", "b - a")], allow_unsealed=True)
    assert env.score_group(task, [GOOD_ADD])["scores"] == [0.0]          # unsealed: not scored unless the demo asks for it
    assert got["scores"] == [1.0, 0.0, 0.0]
    msgs = env.messages_for(task)
    assert msgs[-1]["role"] == "user" and "unified diff" in msgs[-1]["content"] and "assert" not in msgs[-1]["content"]


def _fake_pydantic() -> types.ModuleType:
    """What knos_env and the stub use of pydantic: BaseModel with defaults from class attributes, and Field."""
    mod = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **given):
            for klass in reversed(type(self).__mro__):
                for k, v in vars(klass).items():
                    if not k.startswith("_") and not callable(v):
                        setattr(self, k, v)
            for k, v in given.items():
                setattr(self, k, v)
    mod.BaseModel = BaseModel
    mod.Field = lambda default=None, **kw: default
    return mod


@pytest.fixture()
def stub_atroposlib(monkeypatch):
    try:
        import pydantic
    except ImportError:                     # not a dependency of knos: stand in for the two names used
        pydantic = _fake_pydantic()
        monkeypatch.setitem(sys.modules, "pydantic", pydantic)

    class BaseEnvConfig(pydantic.BaseModel):
        group_size: int = 4
        tokenizer_name: str = "none"
        use_wandb: bool = False
        total_steps: int = 1
        batch_size: int = -1
        steps_per_eval: int = 100
        max_token_length: int = 2048
        wandb_name: str | None = None

    class BaseEnv(abc.ABC):
        name = None
        env_config_cls = BaseEnvConfig

        def __init__(self, config, server_configs, slurm=False, testing=False):
            self.config = config

        @abc.abstractmethod
        async def get_next_item(self): ...

        @abc.abstractmethod
        async def evaluate(self, *args, **kwargs): ...

        async def wandb_log(self, wandb_metrics=None):
            self.logged = wandb_metrics

    class APIServerConfig(pydantic.BaseModel):
        model_name: str = ""
        base_url: str = ""
        api_key: str = ""
        num_requests_for_eval: int = 0

    base = types.ModuleType("atroposlib.envs.base")
    base.BaseEnv, base.BaseEnvConfig, base.APIServerConfig, base.ScoredDataGroup = BaseEnv, BaseEnvConfig, APIServerConfig, dict
    tok = types.ModuleType("atroposlib.utils.tokenize_for_trainer")
    tok.tokenize_for_trainer = lambda tokenizer, chat, **kw: {"tokens": [len(m["content"]) for m in chat], "masks": [1] * len(chat)}
    for name, mod in {"atroposlib": types.ModuleType("atroposlib"), "atroposlib.envs": types.ModuleType("atroposlib.envs"),
                      "atroposlib.envs.base": base, "atroposlib.utils": types.ModuleType("atroposlib.utils"),
                      "atroposlib.utils.tokenize_for_trainer": tok}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    yield base
    sys.modules.pop("knos_env", None)


def test_with_atroposlib_the_env_implements_the_base_and_scores_a_group(stub_atroposlib):
    env = _load_env()
    cls = env.KnosSealedEnv
    assert issubclass(cls, stub_atroposlib.BaseEnv) and cls.name == "knos_sealed" and not getattr(cls, "__abstractmethods__", set())
    config, servers = cls.config_init()
    assert config.group_size == 4 and config.use_wandb is False and len(servers) == 1
    e = cls(config, servers)

    answers = [GOOD_ADD, "nothing", GOOD_ADD, GOOD_ADD.replace("a + b", "0")]

    class Server:
        async def chat_completion(self, **kw):
            n = kw.get("n", 1)
            pick = answers[:n] if n > 1 else [GOOD_ADD]
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=a)) for a in pick])
    e.server, e.tokenizer = Server(), object()
    with pytest.raises(RuntimeError, match="without a seal"):         # the synthetic tasks carry no seal
        asyncio.run(e.setup())
    e.config.allow_unsealed = True

    async def go():
        await e.setup()
        item = await e.get_next_item()
        group, backlog = await e.collect_trajectories(item)
        await e.evaluate()
        await e.wandb_log({})
        return item, group, backlog
    item, group, backlog = asyncio.run(go())
    assert item["id"] == "synthetic-add" and backlog == []
    assert group["scores"] == [1.0, 0.0, 1.0, 0.0] and len(group["tokens"]) == len(group["masks"]) == 4
    assert e.logged["eval/knos_pass_rate"] == 0.5       # synthetic-add passes, synthetic-slug gets the add patch and fails
