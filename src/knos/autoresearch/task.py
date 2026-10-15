"""An autoresearch task: the researcher's folder, read and sealed.

    <task>/program.md     what the researcher wants, in plain English (agents read it; nothing parses it)
    <task>/idea.md        the starting idea
    <task>/task.json      the terms: the ONE editable file, metric, time budget, keep / re-run / graduation bars, data
    <task>/<editable>     the baseline the loop starts from (e.g. train.py)
    sealed file           what only the referee holds: the seed (synthetic data) or the paths of the hidden sets.
                          task.json commits to its sha256 before the loop starts; a different file is refused.

The spec hash covers program.md, idea.md, task.json, the baseline, the sealed file's hash and the locked judging code's
hash, and is the first thing written to the record: nothing in it may change after an experiment has been judged.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import synth

REQUIRED = ("name", "editable", "metric", "direction", "time_budget_s", "keep_delta", "rerun_tolerance", "min_lift",
            "seeds", "data", "sealed")


class TaskError(ValueError):
    pass


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


@dataclass
class Task:
    root: Path
    spec: dict
    program: str
    idea: str
    baseline: str
    sealed_path: Path
    sealed: dict = field(repr=False)

    @property
    def editable(self) -> str:
        return self.spec["editable"]

    @property
    def maximize(self) -> bool:
        return self.spec["direction"] == "max"

    def better(self, a: float, b: float, by: float = 0.0) -> bool:
        """a beats b by more than `by` in the task's direction."""
        return a > b + by if self.maximize else a < b - by

    def lift(self, new: float, old: float) -> float:
        return new - old if self.maximize else old - new

    def spec_hash(self, judge_hash: str) -> str:
        return sha256_bytes(canonical({
            "program": sha256_bytes(self.program.encode()), "idea": sha256_bytes(self.idea.encode()),
            "task": self.spec, "baseline": sha256_bytes(self.baseline.encode()),
            "sealed": self.spec["sealed"]["sha256"], "judge": judge_hash,
            **({"hidden": self.hidden_sha256()} if self.spec["data"]["kind"] == "csv" else {})}))

    def hidden_sha256(self) -> str:
        """sha256 over the CONTENTS of everything the referee judges with: the sealed file's bytes and, for a csv task,
        every hidden file it names (dev, final). Changing a hidden label after sealing changes it (sealed_changed)."""
        crlf, lf = bytes([13, 10]), bytes([10])
        parts = {"sealed": sha256_bytes(self.sealed_path.read_bytes().replace(crlf, lf))}
        if self.spec["data"]["kind"] == "csv":
            for k in ("dev", "final"):
                parts[k] = sha256_bytes((self.sealed_path.parent / self.sealed[k]).read_bytes().replace(crlf, lf))
        return sha256_bytes(canonical(parts))

    def public(self) -> dict[str, list]:
        """What the agent may see: the public train and validation rows (with labels)."""
        d = self.spec["data"]
        if d["kind"] == "synthetic":
            return {"train": synth.rows(f"public:{d['public_seed']}:train", d["n_train"]),
                    "val": synth.rows(f"public:{d['public_seed']}:val", d["n_val"])}
        return {k: read_csv(self.root / d[k]) for k in ("train", "val")}

    def hidden(self) -> dict[str, list]:
        """What only the referee holds: hidden_dev (judges each experiment) and hidden_final (graduation only)."""
        d, s = self.spec["data"], self.sealed
        if d["kind"] == "synthetic":
            return {"dev": synth.rows(f"sealed:{s['seed']}:dev", d["n_dev"]),
                    "final": synth.rows(f"sealed:{s['seed']}:final", d["n_final"])}
        base = self.sealed_path.parent
        return {k: read_csv(base / s[k]) for k in ("dev", "final")}


def read_csv(path: Path) -> list[tuple[list[float], int]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        head = next(r)
        if head[-1] != "y":
            raise TaskError(f"{path.name}: the last column must be y")
        return [([float(v) for v in row[:-1]], int(row[-1])) for row in r if row]


def load(root: Path | str, sealed: Path | str | None = None) -> Task:
    root = Path(root).resolve()
    try:
        spec = json.loads((root / "task.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise TaskError(f"task.json: {why}") from None
    missing = [k for k in REQUIRED if k not in spec]
    if missing:
        raise TaskError(f"task.json lacks {', '.join(missing)}")
    if spec["direction"] not in ("max", "min"):
        raise TaskError("direction must be max or min")
    if len(spec["seeds"]) < 2 or len(set(spec["seeds"])) != len(spec["seeds"]):
        raise TaskError("seeds: at least two distinct seeds (the second is the re-run)")
    editable = spec["editable"]
    if "/" in editable or "\\" in editable or editable.startswith("."):
        raise TaskError("editable: one file name at the task's top level")
    kind = (spec.get("data") or {}).get("kind")
    if kind not in ("synthetic", "csv"):
        raise TaskError("data.kind: synthetic (rows generated from seeds) or csv (files: see docs/reference/AUTORESEARCH.md)")
    if kind == "csv":
        missing = [k for k in ("train", "val") if not isinstance(spec["data"].get(k), str)]
        if missing:
            raise TaskError(f"a csv task names its public files in task.json data: {', '.join(missing)} missing "
                            "(e.g. \"train\": \"public/train.csv\", \"val\": \"public/val.csv\"; last column y)")
        for k in ("train", "val"):
            if not (root / spec["data"][k]).is_file():
                raise TaskError(f"data.{k}: {spec['data'][k]} is not a file in the task folder")
    sealed_path = Path(sealed) if sealed else root / spec["sealed"]["file"]
    raw = sealed_path.read_bytes().replace(b"\r\n", b"\n")      # the same hash on a Windows checkout
    if sha256_bytes(raw) != spec["sealed"]["sha256"]:
        raise TaskError("the sealed file does not match the hash task.json committed to (refused: spec_tampering)")
    sealed_doc = json.loads(raw)
    if kind == "csv":
        missing = [k for k in ("dev", "final") if not isinstance(sealed_doc.get(k), str)]
        if missing:
            raise TaskError(f"the sealed file of a csv task names the hidden files: {', '.join(missing)} missing "
                            "(e.g. {\"dev\": \"hidden_dev.csv\", \"final\": \"hidden_final.csv\"}, paths beside the sealed file)")
        for k in ("dev", "final"):
            if not (sealed_path.parent / sealed_doc[k]).is_file():
                raise TaskError(f"sealed {k}: {sealed_doc[k]} is not a file beside the sealed file")
    return Task(root=root, spec=spec, program=(root / "program.md").read_text(encoding="utf-8"),
                idea=(root / "idea.md").read_text(encoding="utf-8"),
                baseline=(root / editable).read_text(encoding="utf-8"),
                sealed_path=sealed_path, sealed=json.loads(raw))
