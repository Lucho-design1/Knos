"""`knos reproduce PATH`: the research mode of `knos reproduce` (knos.reproduce dispatches here when given a PATH or
--spec). Returns an exit code: 0 reproduced, 1 contested / failed / incomplete (kept private), 2 the spec is wrong."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import publish as pb
from . import run as rr
from . import spec as sp


def main(target: str, spec_file: str = "", heldout: str = "", out: str = "", say: Callable[[str], None] = print, run=None, version: str = "") -> int:
    repo = Path(target or ".").resolve()
    if not repo.is_dir():
        say(f"{repo} is not a folder: give the research repository's folder")
        return 2
    try:
        spec, sha = sp.load(Path(spec_file) if spec_file else repo)
    except sp.SpecError as why:
        say(f"knos.yml cannot be run: {why}")
        return 2
    if heldout and not Path(heldout).is_dir():
        say(f"--heldout {heldout}: not a folder")
        return 2
    if not version:
        from .. import version as v
        version = v()
    kwargs = {"run": run} if run is not None else {}
    result, logs = rr.reproduce(repo, spec, sha, heldout=Path(heldout) if heldout else None, version=version, **kwargs)
    where = Path(out) if out else repo / ".knos-repro"
    kept = pb.keep(result, logs, where)
    for line in rr.summary(result):
        say(line)
    if result["status"] == "reproduced":
        folder = pb.publish(result, where)
        say(f"Published {folder}: result page index.html, badge.svg; paste badge.md into the README. Result sha256 {result['digest']}.")
        return 0
    say(f"Kept private in {kept}: nothing was published. NOTICE-TO-AUTHORS.md is for the authors only; send it to them privately.")
    return 1
