"""Docs legibility (TASK-CHAMPION T6): a prose paragraph of more than 60 words is split between its sentences into
paragraphs of 60 words at most. No word changes: lists, tables, headings, code, HTML and quotes are left as they are.

    python scripts/split_paragraphs.py [--check] [files...]     (default: README.md, docs/*.md, docs/reference/*.md)
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX = 60
SKIP = ("|", "#", "<", "-", "*", ">", "![", "    ", "\t", "[[")
# documents whose figures must stay in the paragraph that carries their sample, ids and date (scripts/rate_claims.py)
KEEP_WHOLE = ("docs/reference/LOAD.md", "docs/reference/BENCH.md",
              # written whole by their generators (each has its own --check): changed there, never here
              "docs/reference/MANIFEST.md", "docs/reference/SOLANA-COVERAGE.md", "docs/reference/SIBYL-COVERAGE.md",
              "docs/reference/QLOO-COVERAGE.md")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(`\"'0-9])")


def words(text: str) -> int:
    return len(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).split())


def split(para: str) -> list[str]:
    if words(para) <= MAX:
        return [para]
    flat = " ".join(line.strip() for line in para.splitlines())
    sentences, out, cur = SENT.split(flat), [], []
    for s in sentences:
        if cur and words(" ".join(cur + [s])) > MAX:
            out.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    wrap = max(len(line) for line in para.splitlines())
    return ["\n".join(textwrap.wrap(c, width=max(80, wrap), break_long_words=False, break_on_hyphens=False)) for c in out]


def fix(text: str) -> str:
    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i in range(0, len(parts), 2):
        paras = re.split(r"(\n\s*\n)", parts[i])
        for j in range(0, len(paras), 2):
            p = paras[j]
            body = p.strip("\n")
            if not body.strip() or body.lstrip().startswith(SKIP) or re.match(r"\s*\d+\.\s", body):
                continue
            new = "\n\n".join(split(body))
            if new != body:
                paras[j] = p.replace(body, new)
        parts[i] = "".join(paras)
    return "".join(parts)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    files = [Path(a) for a in argv if not a.startswith("--")] or [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")),
                                                                     *sorted((ROOT / "docs" / "reference").glob("*.md"))]
    off = []
    files = [f.resolve() for f in files if f.resolve().relative_to(ROOT).as_posix() not in KEEP_WHOLE]
    for f in files:
        s = f.read_text(encoding="utf-8")
        new = fix(s)
        if new != s:
            off.append(str(f.relative_to(ROOT)))
            if not check:
                f.write_text(new, encoding="utf-8", newline="\n")
    print(("over 60 words: " if check else "split: ") + (f"{len(off)} files" if off else "nothing"))
    return 1 if check and off else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
