"""The coding agent of the Knos x Nebius flow: Nemotron 3 Super on Token Factory WRITES the code and its tests, the
agent RUNS those tests in the task's workspace, and TESTS again after every change until they pass or the rounds run
out. Then, and only then, the work goes to the Knos referee, which judges it on sealed tests the agent never saw.

    run(client, task_dir, workspace, rounds=4)   -> AgentRun (files written, every test run, every model call)

One round = one chat completion (the whole conversation so far: the task, the files, the last test output) -> the
files the model wrote -> written into the workspace (only the paths the task opens: `scope`) -> `python -m pytest`
in the workspace, for real, with a timeout and with no key in its environment. The test output goes back to the
model as the next user turn. With no NEBIUS_API_KEY the model's replies are MOCK (labelled; mock.coding_responder);
the test runs are real either way.

Reply format asked of the model: one fenced block per file, opened with ```file path=<path> (a block opened with
```python whose first line is `# file: <path>` is read the same way).
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sources
from .tokenfactory import TokenFactory

SYSTEM = ("ROLE: coding agent. You solve one programming task in a small Python repository. Write the implementation "
          "AND pytest tests for it. Reply with every file you change as a fenced block opened with ```file path=<path> "
          "and the whole new file inside. Only the paths listed as editable may change. After each reply your tests are "
          "run and you see the output; fix what fails. A sealed acceptance suite you never see decides the outcome, so "
          "do not special-case inputs: implement the rule the task states.")
DEFAULT_SCOPE = ("duration.py", "tests/test_*.py")
SECRET_ENV = ("NEBIUS_API_KEY", "TAVILY_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "KNOS_KEYPAIR", "KNOS_RPC_URL")
_FILE = re.compile(r"```file\s+path=([^\s`]+)[^\n]*\n(.*?)```", re.S)
_PY = re.compile(r"```python\n#\s*file:\s*([^\s]+)\n(.*?)```", re.S)


@dataclass
class TestRun:
    round: int
    passed: bool
    exit_code: int
    seconds: float
    tail: str

    def to_dict(self) -> dict:
        return {"round": self.round, "passed": self.passed, "exit_code": self.exit_code, "seconds": round(self.seconds, 3),
                "tail": self.tail[-1200:]}


@dataclass
class AgentRun:
    model: str
    mode: str
    rounds: int = 0
    files: dict[str, str] = field(default_factory=dict)       # path -> final text the agent wrote
    refused_paths: list[str] = field(default_factory=list)    # paths the model tried to write outside the scope
    tests: list[TestRun] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    finished: bool = False

    def to_dict(self) -> dict:
        return {"model": self.model, "mode": self.mode, "rounds": self.rounds, "files": sorted(self.files),
                "refused_paths": self.refused_paths, "tests": [t.to_dict() for t in self.tests], "calls": self.calls,
                "own_tests_pass": self.finished, **({"label": sources.MOCK} if self.mode == "mock" else {})}


def parse_files(text: str) -> dict[str, str]:
    """The files of one reply: {path: text}, in reply order (a later block for the same path wins)."""
    got: dict[str, str] = {}
    for rx in (_FILE, _PY):
        for path, body in rx.findall(text):
            path = path.strip()
            path = path[2:] if path.startswith("./") else path      # never lstrip: "../x" must stay "../x" (refused)
            got[path] = body if body.endswith("\n") else body + "\n"
    return got


def in_scope(path: str, scope=DEFAULT_SCOPE) -> bool:
    p = Path(path)
    if p.is_absolute() or ".." in p.parts or p.name == "conftest.py":
        return False
    return any(fnmatch.fnmatch(path, g) for g in scope)


def clean_env() -> dict:
    """The environment the agent's tests run in: no provider key, no GitHub token, no wallet path."""
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV and not k.endswith(("_API_KEY", "_TOKEN", "_SECRET"))}
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_tests(workspace: Path, round_: int, timeout: float = 120.0) -> TestRun:
    t0 = time.perf_counter()
    try:
        got = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=workspace,
                             env=clean_env(), capture_output=True, text=True, timeout=timeout)
        code, out = got.returncode, (got.stdout + got.stderr)
    except subprocess.TimeoutExpired:
        code, out = 124, f"the tests ran longer than {timeout:.0f} s and were stopped"
    return TestRun(round_, code == 0, code, time.perf_counter() - t0, out.strip())


def task_prompt(task_text: str, workspace: Path, scope) -> str:
    lines = ["## Task", task_text.strip(), "", "## Editable paths: " + ", ".join(scope), "", "## Repository files"]
    for f in sorted(workspace.rglob("*")):
        if f.is_file() and ".knos" not in f.parts and "__pycache__" not in f.parts and f.suffix in (".py", ".ini", ".toml", ".md"):
            rel = f.relative_to(workspace).as_posix()
            lines += [f"### {rel}", "```", f.read_text(encoding="utf-8", errors="replace")[:8000], "```"]
    return "\n".join(lines)


def run(client: TokenFactory, task_text: str, workspace: Path, *, scope=DEFAULT_SCOPE, rounds: int = 4,
        model: str = sources.SUPER, say=print) -> AgentRun:
    """Write -> run -> test, up to `rounds` model calls. The workspace is changed in place."""
    workspace = Path(workspace)
    out = AgentRun(model, client.mode)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task_prompt(task_text, workspace, scope)}]
    for n in range(1, rounds + 1):
        reply = client.chat(model, messages, max_tokens=6000, temperature=0.2)
        out.rounds = n
        out.calls.append(reply.to_dict())
        messages.append({"role": "assistant", "content": reply.text})
        files = parse_files(reply.text)
        wrote = []
        for path, text in files.items():
            if not in_scope(path, scope):
                out.refused_paths.append(path)
                continue
            dest = workspace / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            out.files[path] = text
            wrote.append(path)
        t = run_tests(workspace, n)
        out.tests.append(t)
        own_tests = any(p.startswith("tests/") for p in out.files)
        say(f"agent round {n}: wrote {', '.join(wrote) or 'nothing'}; its tests {'pass' if t.passed else 'fail'} ({t.seconds:.1f} s)")
        if t.passed and own_tests:
            out.finished = True
            break
        feedback = ("Your tests passed, but you wrote no test of your own under tests/. Add tests."
                    if t.passed else f"The tests failed (exit {t.exit_code}). Output:\n```\n{t.tail[-3000:]}\n```\nFix the code or the tests.")
        if out.refused_paths:
            feedback += "\nThese paths are not editable and were not written: " + ", ".join(sorted(set(out.refused_paths)))
        messages.append({"role": "user", "content": feedback})
    return out
