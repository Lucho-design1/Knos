"""Who proposes the next change. Any agent can; none of them decides (the referee does).

    LocalProposer     the default: deterministic hill-climbing over the CONFIG block of the editable file. No model,
                      no key, no network; the same seed gives the same sequence of proposals.
    CommandProposer   any coding agent behind a command: the prompt (program.md, idea.md, the current best file, the
                      history of verdicts) goes to its stdin; it prints the whole new file (a ```python fenced block
                      is taken if present). Examples, none required:
                          claude -p            (Claude Code, print mode)
                          codex exec -         (Codex CLI, prompt from stdin)
                          hermes chat -q -     (Hermes Agent; check your version's flag for a one-shot query)
                      The agent's key, if any, is the agent's own business: Knos neither reads nor stores it.

A proposer sees only what the agent may see: the public files and, per past experiment, the change, its own
self-reported validation score and the referee's decision (kept / discarded / refused + reasons). Never a hidden score.
"""
from __future__ import annotations

import ast
import json
import random
import re
import shlex
import subprocess
from dataclasses import dataclass, field

CONFIG_RE = re.compile(r"^CONFIG\s*=\s*(\{.*?\})\s*$", re.S | re.M)
FEATURE_LADDER = ("linear", "square", "square+pairs")


@dataclass
class Candidate:
    files: dict[str, str]
    agent: str
    change: str


@dataclass
class Context:
    program: str
    idea: str
    editable: str
    best: str
    history: list[dict] = field(default_factory=list)   # [{iteration, change, agent, decision, reasons, reported}]


def read_config(source: str) -> dict:
    m = CONFIG_RE.search(source)
    if not m:
        raise ValueError("no `CONFIG = {...}` block in the editable file")
    got = ast.literal_eval(m.group(1))
    if not isinstance(got, dict):
        raise ValueError("CONFIG must be a dict literal")
    return got


def write_config(source: str, cfg: dict) -> str:
    body = "{\n" + "".join(f"    {k!r}: {v!r},\n" for k, v in cfg.items()) + "}"
    m = CONFIG_RE.search(source)
    return source[:m.start(1)] + body + source[m.end(1):]


def neighbours(cfg: dict) -> list[tuple[str, dict]]:
    """One-step changes of a CONFIG, each with a one-line description."""
    out = []

    def step(key, value, why=""):
        if key in cfg and cfg[key] != value:
            new = dict(cfg)
            new[key] = value
            out.append((f"{key}: {cfg[key]!r} -> {value!r}{why}", new))

    f = cfg.get("features")
    if f in FEATURE_LADDER and FEATURE_LADDER.index(f) + 1 < len(FEATURE_LADDER):
        step("features", FEATURE_LADDER[FEATURE_LADDER.index(f) + 1])
    if "standardize" in cfg:
        step("standardize", not cfg["standardize"])
    if "lr" in cfg:
        step("lr", round(cfg["lr"] * 2, 6))
        step("lr", round(cfg["lr"] / 2, 6))
    if "epochs" in cfg and cfg["epochs"] < 400:
        step("epochs", cfg["epochs"] * 2)
    if "l2" in cfg:
        for v in (0.0, 0.0001, 0.001, 0.01):
            step("l2", v)
    if "batch" in cfg:
        for v in (16, 64):
            step("batch", v)
    return out


class LocalProposer:
    """Hill-climbing from the referee's current best: try each untried one-step change of CONFIG (in a seeded order);
    after a keep, start again from the new best. Stops (returns None) when every neighbour of the best was tried."""

    name = "local-deterministic"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.tried: set[str] = set()

    def propose(self, ctx: Context) -> Candidate | None:
        cfg = read_config(ctx.best)
        self.tried.add(json.dumps(cfg, sort_keys=True))
        options = neighbours(cfg)
        head = [o for o in options if o[0].startswith("features")]   # the idea says: features first
        rest = [o for o in options if not o[0].startswith("features")]
        self.rng.shuffle(rest)
        for change, new in head + rest:
            key = json.dumps(new, sort_keys=True)
            if key in self.tried:
                continue
            self.tried.add(key)
            return Candidate({ctx.editable: write_config(ctx.best, new)}, self.name, change)
        return None


def prompt(ctx: Context) -> str:
    lines = [ctx.program.strip(), "", "## The idea", ctx.idea.strip(), "",
             f"## The current best {ctx.editable} (the ONLY file you may change)", "```python", ctx.best.rstrip(), "```", "",
             "## Past experiments (the referee decided each; hidden scores are never shown)"]
    for h in ctx.history[-30:]:
        lines.append(f"- #{h['iteration']} {h['change']} -> {h['decision']}"
                     + (f" (your val {h['reported'].get('val_accuracy'):.4f})" if h.get("reported", {}).get("val_accuracy") is not None else "")
                     + (f"; {'; '.join(h['reasons'])}" if h.get("reasons") else ""))
    lines += ["", f"Reply with the complete new {ctx.editable} in one ```python block, and a first line comment "
              "`# change: <one line>` saying what you changed. Nothing else."]
    return "\n".join(lines)


def parse_reply(text: str) -> tuple[str, str]:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    src = (blocks[-1] if blocks else text).strip() + "\n"
    m = re.search(r"#\s*change:\s*(.+)", src)
    return src, (m.group(1).strip() if m else "agent edit")


class CommandProposer:
    """Any agent behind a command line: prompt on stdin, the new file on stdout."""

    def __init__(self, command: str, timeout_s: float = 600.0, runner=subprocess.run):
        self.argv = shlex.split(command)
        if not self.argv:
            raise ValueError("an empty proposer command")
        self.name = "cmd:" + self.argv[0]
        self.timeout_s = timeout_s
        self.runner = runner

    def propose(self, ctx: Context) -> Candidate | None:
        p = self.runner(self.argv, input=prompt(ctx), capture_output=True, text=True, timeout=self.timeout_s)
        if p.returncode != 0 or not p.stdout.strip():
            return None
        src, change = parse_reply(p.stdout)
        return Candidate({ctx.editable: src}, self.name, change)


def from_spec(spec: str, seed: int = 0):
    """'local' or 'cmd:<command line>'."""
    if spec in ("", "local"):
        return LocalProposer(seed)
    if spec.startswith("cmd:"):
        return CommandProposer(spec[4:])
    raise ValueError(f"unknown proposer {spec!r}: use local or cmd:<command>")
