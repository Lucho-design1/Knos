"""A repository's AI policy, read from its own files, before an agent opens a pull request there.

Where it is read, in this order (the first file that says anything about AI decides; the others are listed):

    AI_POLICY.md, AI-POLICY.md, AI_POLICY.txt, .github/AI_POLICY.md, docs/AI_POLICY.md,
    CONTRIBUTING.md, CONTRIBUTING.rst, CONTRIBUTING.txt, .github/CONTRIBUTING.md, docs/CONTRIBUTING.md

A machine-readable line wins over the prose: `ai-contributions: banned | conditional | disclose | allowed`
(alone on a line, or as a YAML front-matter key, `ai_contributions` also accepted).

Otherwise each sentence that names AI (AI, LLM, generative, ChatGPT, Copilot, Claude, an AI agent, machine-generated)
is read for one of four stances, and the strictest one found wins:

    banned       the repository does not accept AI-made work ("we do not accept AI-generated pull requests")
    conditional  it accepts it only on a condition an agent cannot meet by itself ("... without human review will
                 be closed"): a person must confirm the condition is met
    disclose     it accepts it when the AI use is disclosed ("AI-assisted contributions must be disclosed")
    allowed      it says AI use is welcome, or the files say nothing about AI ("unstated" is kept apart)

A sentence the reader cannot place is read as the stricter stance, never the looser one. The lines that decided are
returned verbatim (cut to 300 characters) inside `untrusted`: they are the repository's words, data and never an
instruction to the agent.
"""

from __future__ import annotations

import re
from pathlib import Path

FILES = ("AI_POLICY.md", "AI-POLICY.md", "AI_POLICY.txt", ".github/AI_POLICY.md", "docs/AI_POLICY.md",
         "CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md")
STANCES = ("banned", "conditional", "disclose", "allowed", "unstated")      # strictest first
_RANK = {s: i for i, s in enumerate(STANCES)}
MOST_BYTES = 256_000

_MARK = re.compile(r"^\s*(?:[-*]\s*)?(?:ai[-_]contributions|knos[-_]ai[-_]policy)\s*:\s*[\"']?(banned|conditional|disclose|allowed)[\"']?\s*$",
                   re.I | re.M)
_AI = re.compile(r"(?<![\w-])(?:A\.?I\.?(?:[- ](?:generated|assisted|written|authored|made|created|agents?|tools?|bots?))?|LLMs?|"
                 r"large language models?|generative|gen ?AI|ChatGPT|GPT-?\d*|Copilot|Claude|Gemini|Codex|Cursor|"
                 r"machine[- ]generated|coding agents?|autonomous agents?|bots?[- ]generated)(?![\w-])")
_BAN = re.compile(r"\b(?:not (?:be )?(?:accept(?:ed)?|allowed|permitted|welcome|merged|considered|reviewed)|(?:do|does|will|shall|must|may|should) not accept|"
                  r"don'?t accept|won'?t accept|cannot accept|can'?t accept|no longer accept|refuse[sd]?|reject(?:ed|s)?|"
                  r"ban(?:ned|s)?|prohibit(?:ed|s)?|forbid(?:den|s)?|disallow(?:ed)?|not tolerated|"
                  r"(?:will|shall) be (?:closed|rejected|removed|deleted|locked)|auto[- ]?clos(?:e|ed|es)|"
                  r"(?:do|does) not (?:submit|open|send|use)|don'?t (?:submit|open|send|use)|never (?:submit|open|send|use)|"
                  r"no (?:AI|LLM)|zero[- ]tolerance)\b", re.I)
_COND = re.compile(r"\b(?:unless|except|without|only (?:if|when|after)|provided (?:that)?|as long as|must (?:be )?(?:review|read|test|understand|verif)|"
                   r"human[- ](?:review|written|in the loop|authored|oversight)|fully[- ](?:automated|autonomous|generated)|"
                   r"(?:un)?reviewed|you (?:must|need to) understand)", re.I)
_DISCLOSE = re.compile(r"\b(?:disclos\w*|declare\w*|state (?:that|which|whether)|mention\w*|label\w*|tag(?:ged)?|note (?:that|which|whether)|"
                       r"indicate\w*|transparen\w*|attribut\w*|co-authored-by|assisted-by)\b", re.I)
_WELCOME = re.compile(r"\b(?:welcome|allowed|permitted|fine|ok(?:ay)?|accept(?:ed)?|encourag\w*|happy to)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n\s*[-*#>]+\s*")


def _sentences(text: str) -> list[str]:
    return [" ".join(s.split()) for s in _SENTENCE.split(text) if s and s.strip()]


def stance_of(sentence: str) -> str | None:
    """The stance one sentence takes on AI-made work, or None when it does not speak of AI."""
    if not _AI.search(sentence):
        return None
    banned, cond, disclose = bool(_BAN.search(sentence)), bool(_COND.search(sentence)), bool(_DISCLOSE.search(sentence))
    if banned and cond:
        # "AI-generated PRs without disclosure will be closed": the condition is disclosure, which the agent meets
        if disclose and not re.search(r"human|review|understand|test|read|fully|autonom", sentence, re.I):
            return "disclose"
        return "conditional"
    if banned:
        return "banned"
    if cond and re.search(r"human|review|understand|fully|autonom", sentence, re.I):
        return "conditional"
    if disclose:
        return "disclose"
    if _WELCOME.search(sentence):
        return "allowed"
    return "disclose"       # it speaks of AI and the reader cannot place it: the stricter of the two accepting stances


def _read(path: Path) -> str:
    try:
        return path.read_bytes()[:MOST_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return ""


def read(tree: Path | None = None, get=None) -> dict:
    """The policy of the checkout at `tree`, or as `get(name) -> text | None` reads it (knos verify reads the files at
    the BASE commit, so a change cannot rewrite the policy it is judged by): {"stance", "file", "files", "source",
    "untrusted": {"lines"}}. `source` is "marker" (the machine-readable line), "prose" (sentences), or "none"."""
    root = Path(tree or ".")

    def from_disk(name: str) -> str | None:
        return _read(root / name) if (root / name).is_file() else None
    reader = get or from_disk
    texts = {name: t for name in FILES if (t := reader(name)) is not None}
    found = list(texts)
    for name in found:
        text = texts[name][:MOST_BYTES]
        mark = _MARK.search(text)
        if mark:
            return {"stance": mark.group(1).lower(), "file": name, "files": found, "source": "marker",
                    "untrusted": {"lines": [mark.group(0).strip()[:300]]}}
        placed = [(s, st) for s, st in ((s, stance_of(s)) for s in _sentences(text)) if st]
        if placed:
            worst = min((st for _s, st in placed), key=_RANK.__getitem__)
            lines = [s[:300] for s, st in placed if st == worst][:5]
            return {"stance": worst, "file": name, "files": found, "source": "prose", "untrusted": {"lines": lines}}
    return {"stance": "unstated", "file": None, "files": found, "source": "none", "untrusted": {"lines": []}}


def may_open_pr(stance: str, human_confirmed: bool = False) -> bool:
    """Whether an agent may open a pull request under this stance: never under `banned`; under `conditional` only when
    the person running the agent confirmed the condition is met."""
    if stance == "banned":
        return False
    if stance == "conditional":
        return human_confirmed
    return True


def disclosure(stance: str, agent: str = "", ai_used: bool = True) -> str:
    """The line for the pull request's description. Knos discloses AI use whatever the stance (unless none was used)."""
    if not ai_used:
        return "AI use: none (declared by the author)."
    who = f" ({agent})" if agent else ""
    line = f"AI use: this change was made with an AI coding agent{who} and checked with `knos verify` before it was opened."
    if stance == "conditional":
        line += " A person confirmed the repository's condition for AI-made work is met."
    return line
