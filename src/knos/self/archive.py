"""The archive: every version the loop tried, with its lineage, and the choice of which version agents build on next.

Like the Darwin Goedel Machine (arXiv 2505.22954) the loop keeps every version, not only the best one. Like the
Huxley-Goedel Machine (arXiv 2510.21614) it chooses the parent by how the parent's DESCENDANTS did (its clade), not by
the parent's own score: a version whose children keep getting accepted is a better place to build than one with a good
number and a line of refused children. Each eligible version gets Beta(1 + accepted, 1 + refused) over its clade and
one seeded Thompson draw; the highest draw is the parent. The seed and every draw are kept, so the choice can be
re-computed by anyone from the archive file.

Node decisions: root | canary (accepted, on the loop branch, bounty paid) | promoted (the founder merged it to main) |
held (founder review: cap reached, implausible gain, shadow disagreement) | refused | rolled_back.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path

ACCEPTED = ("root", "canary", "promoted")
FAILED = ("refused", "rolled_back")
DECISIONS = ACCEPTED + FAILED + ("held",)


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"v": 1, "nodes": [], "choices": []}

    # ---- nodes ---------------------------------------------------------------------------------------------------
    @property
    def nodes(self) -> list[dict]:
        return self.data["nodes"]

    def get(self, vid: str) -> dict:
        for n in self.nodes:
            if n["id"] == vid:
                return n
        raise KeyError(f"no version {vid} in the archive")

    def next_id(self) -> str:
        return f"v{len(self.nodes)}"

    def add(self, node: dict) -> dict:
        if node.get("decision") not in DECISIONS:
            raise ValueError(f"decision {node.get('decision')!r}: one of {', '.join(DECISIONS)}")
        if node.get("parent") is not None:
            self.get(node["parent"])
        node = {"id": node.get("id") or self.next_id(), "ts": node.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **node}
        node["day"] = node["ts"][:10]
        if any(n["id"] == node["id"] for n in self.nodes):
            raise ValueError(f"version {node['id']} exists")
        self.nodes.append(node)
        return node

    def root(self, commit: str, *, target: str = "", metric=None, judge_hash: str = "") -> dict:
        if self.nodes:
            return self.nodes[0]
        return self.add({"id": "v0", "parent": None, "commit": commit, "decision": "root", "target": target,
                         "metric": metric, "judge_hash": judge_hash, "agent": "main"})

    def children(self, vid: str) -> list[dict]:
        return [n for n in self.nodes if n.get("parent") == vid]

    def descendants(self, vid: str) -> list[dict]:
        out, todo = [], [vid]
        while todo:
            kids = self.children(todo.pop())
            out += kids
            todo += [k["id"] for k in kids]
        return out

    def lineage(self, vid: str) -> list[str]:
        out = []
        cur: str | None = vid
        while cur is not None:
            out.append(cur)
            cur = self.get(cur).get("parent")
        return out

    def set(self, vid: str, **fields) -> dict:
        n = self.get(vid)
        n.update(fields)
        return n

    def merged_on(self, day: str) -> int:
        return sum(1 for n in self.nodes if n.get("decision") in ("canary", "promoted") and n.get("canary_day", n.get("day")) == day)

    # ---- the parent ----------------------------------------------------------------------------------------------
    def clade(self, vid: str) -> dict:
        """Accepted and failed versions among the descendants of `vid` (held ones count as neither)."""
        d = self.descendants(vid)
        return {"accepted": sum(n["decision"] in ACCEPTED for n in d), "failed": sum(n["decision"] in FAILED for n in d),
                "size": len(d)}

    def eligible(self, target: str | None = None) -> list[dict]:
        return [n for n in self.nodes if n["decision"] in ACCEPTED and (target is None or n["decision"] == "root" or n.get("target") == target)]

    def choose_parent(self, target: str | None = None, *, seed: int | None = None, record: bool = True) -> dict:
        """The HGM choice: one Thompson draw from Beta(1 + accepted, 1 + failed) of each eligible version's clade."""
        pool = self.eligible(target)
        if not pool:
            raise ValueError("the archive has no accepted version to build on (run `knos self init` first)")
        seed = seed if seed is not None else int(hashlib.sha256(json.dumps([n["id"] for n in self.nodes]).encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        draws = []
        for n in pool:
            c = self.clade(n["id"])
            a, b = 1 + c["accepted"], 1 + c["failed"]
            draws.append({"id": n["id"], "alpha": a, "beta": b, "mean": round(a / (a + b), 4), "draw": round(rng.betavariate(a, b), 6)})
        best = max(draws, key=lambda d: (d["draw"], d["mean"], d["id"]))
        choice = {"target": target, "seed": seed, "draws": draws, "parent": best["id"], "n_versions": len(self.nodes)}
        if record:
            self.data.setdefault("choices", []).append(choice)
        return choice

    def best(self, target: str, direction: str = "lower") -> dict | None:
        got = [n for n in self.nodes if n["decision"] in ("canary", "promoted") and n.get("target") == target and n.get("metric") is not None]
        if not got:
            return None
        return (min if direction == "lower" else max)(got, key=lambda n: n["metric"])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
