"""Nemotron 3 Super as a Knos coder. It proposes; it never decides.

    NemotronProposer   a knos.autoresearch proposer: the same prompt CommandProposer sends (program, idea, the current
                       best file, the referee's past decisions, never a hidden score), one chat completion, the whole new
                       file back. Plug it into knos.autoresearch.run like LocalProposer.
    self_diff          a knos.self coder: the target's description and its in-scope files -> one unified diff.
    prescreen          the referee's static half on that diff before any of it runs: knos.self's path rules (trusted
                       core, product paths) + knos.cheats.scan_diff with the target's scope and the core. A diff that
                       passes still has to go through `knos self run` (sealed tier, re-runs, daily cap, founder rules).
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import cheats
from ..autoresearch import proposers
from . import sources
from .tokenfactory import TokenFactory

AR_SYSTEM = ("ROLE: autoresearch coder. You improve one Python file for a task. The Knos referee judges every change on "
             "data you never see and refuses cheats (other files, new imports, reading sealed data). Return the whole file.")
SELF_SYSTEM = ("ROLE: knos self coder. You propose one small change to the Knos repository for the named target. Only the "
               "listed files may change. Reply with one unified diff (git format) in a ```diff block and nothing else.")


class NemotronProposer:
    """knos.autoresearch proposer backed by a Token Factory model (Nemotron 3 Super by default)."""

    def __init__(self, client: TokenFactory, model: str = sources.SUPER, *, max_tokens: int = 8192):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.name = "nemotron-3-super" if model == sources.SUPER else "tokenfactory:" + model

    def propose(self, ctx: proposers.Context) -> proposers.Candidate | None:
        reply = self.client.chat(self.model, [{"role": "system", "content": AR_SYSTEM},
                                              {"role": "user", "content": proposers.prompt(ctx)}], max_tokens=self.max_tokens)
        if not reply.text.strip():
            return None
        src, change = proposers.parse_reply(reply.text)
        return proposers.Candidate({ctx.editable: src}, self.name, change)


def self_prompt(target: dict, files: dict[str, str], max_chars: int = 20_000) -> str:
    lines = [f"## Target {target['id']}", str(target.get("what", "")), f"Metric: {target.get('metric', '')} "
             f"(direction: {target.get('direction', '')})", "", "## Files you may change"]
    for path, text in files.items():
        lines += [f"### {path}", "```python", text[:max_chars], "```"]
    lines += ["", "Reply with one unified diff in a ```diff block. The first line inside the block is a comment "
              "`# change: <one line>`."]
    return "\n".join(lines)


def self_diff(client: TokenFactory, target: dict, root: Path, model: str = sources.SUPER) -> dict:
    files = {}
    for p in target.get("scope") or []:
        f = Path(root) / p
        if f.is_file():
            files[p] = f.read_text(encoding="utf-8", errors="replace")
    reply = client.chat(model, [{"role": "system", "content": SELF_SYSTEM},
                                {"role": "user", "content": self_prompt(target, files)}], max_tokens=8192)
    blocks = re.findall(r"```(?:diff|patch)?\s*\n(.*?)```", reply.text, re.S)
    body = (blocks[-1] if blocks else reply.text).strip("\n") + "\n"
    m = re.match(r"#\s*change:\s*(.+)\n", body)
    change = m.group(1).strip() if m else "agent diff"
    diff = body[m.end():] if m else body
    return {"diff": diff, "change": change, "reply": reply}


def prescreen(diff: str, cfg: dict, target: dict) -> dict:
    """knos self check-pr, as a function: path rules + the cheat library on the diff, nothing executed."""
    from ..self import config
    scope = tuple(target.get("scope") or ())
    paths = sorted({f.path for f in cheats.parse_diff(diff)})
    found = config.agent_findings(paths, cfg, scope) + cheats.scan_diff(diff, scope=scope, core=tuple(config.core_globs(cfg)))
    return {"refused": cheats.refused(found), "findings": [f.to_dict() for f in found], "paths": paths}
