"""Knos as a Hermes memory provider.

Hermes keeps one memory per agent. Knos keeps one memory per *repo*, shared
by every coding agent on the machine — Hermes, Claude Code, Cursor,
OpenCode — and it knows which of them is working on what right now.

So this provider is thin on purpose. It does not store anything of its own:
recall and writes go to the same SQLite file `knos` already uses, which
means a decision Hermes records here is visible to Claude Code in the next
breath, and a piece of work another agent has claimed is withheld from
Hermes the same way it is withheld from them.

Discovery: Hermes scans `$HERMES_HOME/plugins/<name>/` for a directory whose
`__init__.py` mentions `MemoryProvider` or `register_memory_provider`. It
does not read pip entry points, whatever CONTRIBUTING says — see
`plugins/memory/__init__.py` in hermes-agent. `knos-hermes install` copies
this directory into place, which is why the package ships it as data rather
than relying on an entry point that is never consulted.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

# What a recall injects at most. Hermes puts this straight into the prompt,
# and a memory block that crowds out the conversation is worse than none.
MAX_RECALL_CHARS = 1200
MAX_HITS = 6


def _repo() -> Path | None:
    """The repo Knos answers for, or None if we are not in one.

    Knos resolves this itself: the working tree you are standing in wins,
    and every worktree of a repo shares one memory.
    """
    try:
        from knos import paths

        return paths.current_repo()
    except Exception:  # pragma: no cover - knos missing is reported by is_available
        return None


class KnosMemoryProvider(MemoryProvider):
    """Hermes talks to the memory every other agent on the machine uses."""

    def __init__(self) -> None:
        self._session_id = ""
        self._prefetched = ""

    # ---- identity ------------------------------------------------------

    @property
    def name(self) -> str:
        return "knos"

    def is_available(self) -> bool:
        """Installed, and standing somewhere Knos can answer for.

        No API key, no server, no network check — there is nothing to reach.
        """
        try:
            import knos  # noqa: F401
        except ImportError:
            return False
        return _repo() is not None

    def get_config_schema(self):
        """Nothing to configure. Said explicitly so the setup wizard shows why."""
        return []

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        return None

    def post_setup(self, hermes_home: str, config: Dict[str, Any]) -> str:
        repo = _repo()
        if repo is None:
            return (
                "Knos answers per repository. Start Hermes inside a git repo,"
                " or run `knos point /path/to/repo` once."
            )
        return f"Knos is answering from {repo.name}. Nothing else to set up."

    # ---- lifecycle -----------------------------------------------------

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id or ""

    def system_prompt_block(self) -> str:
        return (
            "You share one local memory with every other coding agent on this"
            " machine (Claude Code, Cursor, OpenCode). Before you change"
            " anything, call knos_claim with a short description of the work,"
            " so the others are held off it. If knos_recall tells you work is"
            " withheld, ask the person rather than guessing."
        )

    def shutdown(self) -> None:
        """Release anything this session was holding.

        A claim lapses on its own after thirty minutes, but an agent that
        exits cleanly should not leave other agents blocked until then.
        """
        repo = _repo()
        if repo is None:
            return
        try:
            from knos.memory import Memory

            with Memory(repo) as mem:
                mem.done_working()
        except Exception as why:  # pragma: no cover - shutdown must not raise
            logger.debug("knos: nothing to release (%s)", why)

    # ---- recall --------------------------------------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """What the shared memory already knows about this turn's question.

        Synchronous and local: this is a SQLite read, not a network call, so
        there is nothing to do in a background thread that would not cost
        more in coordination than it saves.
        """
        repo = _repo()
        if repo is None or not (query or "").strip():
            return ""
        try:
            from knos import answer as knos_answer
            from knos.memory import Memory

            with Memory(repo) as mem:
                found = knos_answer.ask(repo, mem, query, limit=MAX_HITS)
        except Exception as why:
            logger.debug("knos: recall failed (%s)", why)
            return ""
        if not found:
            return ""

        lines: List[str] = []
        used = 0
        for hit in found:
            text = hit.text.strip()
            block = f"- {text}\n  source: {hit.where}"
            if used + len(block) > MAX_RECALL_CHARS:
                break
            lines.append(block)
            used += len(block)
        if not lines:
            return ""
        self._prefetched = "\n".join(lines)
        return "## Knos (shared with your other agents)\n" + self._prefetched

    # ---- writes --------------------------------------------------------

    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        """Knos reads Hermes transcripts itself; nothing is written per turn.

        Every other provider writes each turn to its own store. Knos does not
        need to: `knos point` reads the session history already on disk, so
        writing it a second time would duplicate what the next read finds
        anyway and spend the 5 MB budget twice. What Hermes writes here is
        only what an agent *chose* to record, through the tools below.
        """
        return None

    # ---- tools ---------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "knos_recall",
                "description": (
                    "Search the memory shared by every coding agent on this"
                    " machine: past sessions, commits, CLAUDE.md and AGENTS.md,"
                    " decision records. Every result names its source. Work"
                    " another agent has claimed is withheld."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What you want to know"}
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "knos_remember",
                "description": (
                    "Write one fact into the shared memory so every other agent"
                    " on this machine has it too."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "fact": {"type": "string", "description": "The thing worth keeping"},
                        "about": {"type": "string", "description": "What to file it under"},
                    },
                    "required": ["fact"],
                },
            },
            {
                "name": "knos_claim",
                "description": (
                    "Say what you are about to change. Every other agent on this"
                    " machine is then refused answers about it until you call"
                    " knos_done, or thirty minutes pass."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "work": {"type": "string", "description": "What you are working on"}
                    },
                    "required": ["work"],
                },
            },
            {
                "name": "knos_done",
                "description": "Release what you claimed, so the others can ask about it again.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        repo = _repo()
        if repo is None:
            return "Knos is not in a git repo here, so there is nothing to read."

        from datetime import datetime, timezone

        from knos import answer as knos_answer
        from knos.memory import TOPIC, Fact, Memory

        now = datetime.now(timezone.utc).isoformat()
        try:
            if tool_name == "knos_recall":
                query = str(args.get("query") or "")
                with Memory(repo) as mem:
                    held = self._withheld(mem, query)
                    if held:
                        return held
                    found = knos_answer.ask(repo, mem, query, limit=MAX_HITS)
                if not found:
                    return "Nothing known about that."
                return "\n\n".join(f"{h.text.strip()}\n    source: {h.where}" for h in found)

            if tool_name == "knos_remember":
                fact = str(args.get("fact") or "").strip()
                if not fact:
                    return "Nothing to remember."
                about = str(args.get("about") or "") or knos_answer.topic_of(fact)
                with Memory(repo) as mem:
                    mem.record(
                        Fact(
                            text=fact,
                            source="note",
                            where=f"Hermes said so, {now[:10]}",
                            when=now,
                            about=about,
                        )
                    )
                    mem.note_thing(TOPIC, about, {"note": fact, "when": now[:10]})
                return f"Remembered, under {about}. Every agent here now has it."

            if tool_name == "knos_claim":
                work = str(args.get("work") or "").strip()
                if not work:
                    return "Say what you are claiming."
                with Memory(repo) as mem:
                    mem.working_on(work, "Hermes", now, session=str(os.getpid()))
                return (
                    f"Claimed {work}. Every other agent on this machine is now"
                    " refused answers about it until knos_done."
                )

            if tool_name == "knos_done":
                with Memory(repo) as mem:
                    mem.done_working()
                return "Released. The others can ask about it again."
        except Exception as why:
            logger.debug("knos: tool %s failed (%s)", tool_name, why)
            return f"Knos could not do that: {why}"

        return f"Unknown tool: {tool_name}"

    # ---- the part that makes it coordination, not a notice board -------

    def _withheld(self, mem: Any, query: str) -> str:
        """Refuse to be the source for work another agent is mid-change on."""
        try:
            from knos.answer import same_subject, withheld
        except Exception:  # pragma: no cover - older knos
            return ""
        blocked = []
        for work in mem.claims():
            topic = str(work.get("topic", ""))
            who = str(work.get("who", ""))
            if who == "Hermes" or not same_subject(topic, query):
                continue
            blocked.append((topic, who or "another agent"))
        if not blocked:
            return ""
        by_person = all(w == "you" for _, w in blocked)
        held = (
            "; ".join(t for t, _ in blocked)
            if by_person
            else "; ".join(f"{t} (held by {w})" for t, w in blocked)
        )
        return withheld(held, by_person)


def register(ctx) -> None:
    """Hermes calls this when the plugin directory is loaded."""
    ctx.register_memory_provider(KnosMemoryProvider())
