"""Task packages: a maintainer exports a merged issue + pull request as a sealed, verified, reward-hack-resistant task.

    knos taskpack export owner/repo#PR --repo-dir CLONE [--opt-in] [--encrypt]
    knos taskpack verify PACK | grade PACK --patch FILE --repo-dir CLONE | rows PACK... --out tasks.jsonl

knos.taskpack.export builds and checks packages; knos.taskpack.grade grades a candidate patch (cheat rules, then the hidden
tests); knos.taskpack.atropos turns packages into training rows and a referee spec. docs/reference/REFEREE.md.
"""
from __future__ import annotations

from .export import FORMAT, Refused, load, verify  # noqa: F401  (export, grade: the modules)


def register(app, help_lines: list | None = None) -> None:
    from . import cli
    cli.register(app, help_lines)
