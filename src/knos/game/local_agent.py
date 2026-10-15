"""A command-line agent with no model, for the generic command protocol (prompt on stdin, the whole file on stdout).

    python -m knos.game.local_agent < prompt.txt

LABEL: "local deterministic agent (no model)". It reads the current best file from the prompt's ```python block and
the number of past attempts from its history lines, and answers the next one-step change of the CONFIG block
(knos.autoresearch.proposers.neighbours, features first). It shows that any program speaking the protocol can play;
it is not an AI scientist.
"""
from __future__ import annotations

import re
import sys

from ..autoresearch import proposers

LABEL = "local deterministic agent (no model)"


def answer(prompt: str) -> str:
    blocks = re.findall(r"```python\n(.*?)```", prompt, re.S)
    if not blocks:
        return ""
    best = blocks[0]
    tried = len(re.findall(r"^- #\d+", prompt, re.M))
    options = proposers.neighbours(proposers.read_config(best))
    options = [o for o in options if o[0].startswith("features")] + [o for o in options if not o[0].startswith("features")]
    if not options:
        return ""
    change, new = options[tried % len(options)]
    return f"```python\n# change: {change}\n{proposers.write_config(best, new)}```\n"


def main() -> int:
    out = answer(sys.stdin.read())
    sys.stdout.write(out)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
