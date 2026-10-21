"""docs/submission/UPDATES.md: the dated log of every change since the hackathon opened (30 Sep 2026), from git.

    python scripts/submission_log.py           write it: every commit on main from 2026-09-30 to HEAD, by day
    python scripts/submission_log.py --check   exit 1 unless the file lists every commit from 2026-09-30 up to the
                                               commit before the one that last wrote it (a file cannot list itself)

The Devpost rules ask an existing project to "explain how their Project was significantly updated during the
Submission Period"; this is that record, as git has it, nothing typed by hand.
"""
from __future__ import annotations

import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "submission" / "UPDATES.md"
SINCE = "2026-09-30"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def commits(until: str = "HEAD") -> list[tuple[str, str, str, str]]:
    """(day, short sha, author, subject), oldest first."""
    out = git("log", "--reverse", f"--since={SINCE}", "--format=%ad%x1f%h%x1f%an%x1f%s", "--date=short", until)
    return [tuple(line.split("\x1f")) for line in out.splitlines() if line.strip()]  # type: ignore[misc]


def render(rows) -> str:
    days: OrderedDict[str, list] = OrderedDict()
    for day, sha, who, subject in rows:
        days.setdefault(day, []).append((sha, who, subject))
    out = ["# Knos: what changed during the hackathon", "",
           f"Every commit on `main` since the Submission Period opened ({SINCE}), by day, from `git log` "
           "(`scripts/submission_log.py`). Each line links its commit.", "",
           f"{len(rows)} commits over {len(days)} days.", ""]
    for day, items in days.items():
        out.append(f"## {day} ({len(items)})")
        out.append("")
        for sha, who, subject in items:
            out.append(f"- [`{sha}`](https://github.com/drexthealpha/Knos/commit/{sha}) {subject.replace('|', '/')}"
                       + ("" if who == "drexthealpha" else f" (by {who})"))
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        last = git("log", "-1", "--format=%H", "--", str(OUT.relative_to(ROOT))).strip()
        if not last or not OUT.exists():
            print("docs/submission/UPDATES.md is not written yet")
            return 1
        want = [sha for _d, sha, _w, _s in commits(last + "^")]
        text = OUT.read_text(encoding="utf-8")
        gone = [s for s in want if f"`{s}`" not in text]
        print(f"UPDATES.md lists {len(want) - len(gone)} of the {len(want)} commits before it" + (f"; missing {gone[:5]}" if gone else ""))
        return 1 if gone else 0
    rows = commits()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} commits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
