"""Sealing: what is fixed before any work starts, and checked again before any verdict.

    spec_hash    knos.judge.checks_hash of the hidden acceptance bundle (the sealed tests). The worker never sees the
                 bundle; the hash is published, so anyone can later check the tests that judged were the ones sealed.
    judge_hash   the hash of the judging code itself (knos/judge.py, knos/referee/**, knos/cheats/**) of the install
                 that sealed. A verdict is given only by an install whose judging code has the same hash, so a worker
                 who edits the referee in its own pull request changes nothing: the referee that runs is main's.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

_KNOS = Path(__file__).resolve().parents[1]
JUDGING_CODE = ("judge.py", "referee", "cheats")


def judge_hash(paths=None) -> str:
    """sha256 over the locked judging code, in judge.checks_hash's form (sorted "path\\0sha256\\n" lines). `paths`:
    other files or folders to hash instead (relative names are under the running knos package)."""
    roots = [(_KNOS / p) if not Path(p).is_absolute() else Path(p) for p in (paths or JUDGING_CODE)]
    files: list[tuple[str, Path]] = []
    for root in roots:
        if root.is_file():
            files.append((root.name if root.parent == _KNOS else root.as_posix(), root))
        elif root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    files.append((p.relative_to(root.parent).as_posix(), p))
    if not files:
        raise ValueError("no judging code found to hash")
    crlf, lf = b"\r\n", b"\n"          # the same code checked out on Windows hashes the same
    lines = "".join(name + "\0" + hashlib.sha256(p.read_bytes().replace(crlf, lf)).hexdigest() + "\n"
                    for name, p in sorted(files))
    return hashlib.sha256(lines.encode()).hexdigest()


def seal(bundle_dir, *, issue: str, scope=(), test_dirs=None, tolerance=None, reruns: int = 1, at: float | None = None) -> dict:
    """The sealed spec of one task: published before work starts (its hash goes on the order / issue comment).
    `bundle_dir`: the hidden acceptance bundle (kept outside the repository: a private repo or a secret).
    `tolerance`: {"abs": float, "rel": float} for a numeric metric a re-run must reproduce."""
    from ..judge import checks_hash
    out = {"v": 1, "issue": str(issue), "spec_hash": checks_hash(Path(bundle_dir)), "judge_hash": judge_hash(),
           "scope": sorted(str(s) for s in scope), "test_dirs": list(test_dirs) if test_dirs else None,
           "tolerance": dict(tolerance) if tolerance else {"abs": 0.0, "rel": 0.0}, "reruns": int(reruns),
           "sealed_at": int(at if at is not None else time.time())}
    return out


def seal_hash(sealed: dict) -> str:
    """sha256 of the canonical JSON of a seal: the one value both parties sign."""
    return hashlib.sha256(json.dumps(sealed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
