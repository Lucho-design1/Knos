"""targets.yml and CODEOWNERS: what the loop works on, and the line between the trusted core and the product.

The loop reads both files from MAIN only (the trusted checkout the referee runs from), never from a candidate: a
candidate that edits either file is refused as a core-path change before any of its code runs.

    load(root)                    targets.yml of a tree, validated (TargetsError lists every problem)
    codeowners_globs(text)        the paths a CODEOWNERS file gives an owner, as globs
    classify(path, cfg)           "core" | "product" | "outside"
    agent_findings(paths, cfg)    one finding per path an agent may not change (core, or outside the product)
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import cheats as _cheats

TARGETS = "targets.yml"
CODEOWNERS = "CODEOWNERS"
ROLLOUT = ("sealed", "shadow", "canary", "main")
KINDS = ("product", "referee")
STATUSES = ("open", "proposed", "paused", "founder-only", "closed")
_ID = re.compile(r"^[a-z][a-z0-9-]{1,47}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_USD = re.compile(r"^\d+(\.\d{1,6})?$")


class TargetsError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("targets.yml: " + "; ".join(self.problems))


def _read_yaml(path: Path) -> dict:
    from ..money.fees_config import read
    return read(path)


def validate(doc) -> list[str]:
    p: list[str] = []
    if not isinstance(doc, dict):
        return ["the file is not a mapping"]
    if doc.get("version") != 1:
        p.append("version: 1")
    if not isinstance(doc.get("founder"), str) or not doc.get("founder"):
        p.append("founder: the GitHub login that owns the trusted core")
    loop = doc.get("loop") or {}
    if not isinstance(loop.get("daily_merge_cap"), int) or isinstance(loop.get("daily_merge_cap"), bool) or loop["daily_merge_cap"] < 0:
        p.append("loop.daily_merge_cap: a whole number from 0")
    if tuple(loop.get("rollout") or ()) != ROLLOUT:
        p.append("loop.rollout: exactly " + " -> ".join(ROLLOUT))
    if loop.get("auto_merge_to_main") is not False:
        p.append("loop.auto_merge_to_main: false (turning it on is the founder's decision, made by hand on main)")
    if loop.get("network") not in ("devnet", "localnet"):
        p.append("loop.network: devnet or localnet (no mainnet, no real money)")
    if not _USD.match(str(loop.get("canary_bounty_max_usd", ""))):
        p.append("loop.canary_bounty_max_usd: a decimal string")
    rc = loop.get("referee_change") or {}
    if rc.get("red_team") != "at_least_current":
        p.append("loop.referee_change.red_team: at_least_current")
    if not isinstance(rc.get("approval_keys", []), list):
        p.append("loop.referee_change.approval_keys: a list of base58 ed25519 keys")
    for key in ("core", "product"):
        if not isinstance(doc.get(key), list) or not all(isinstance(g, str) and g for g in doc[key]):
            p.append(f"{key}: a list of path globs")
    for need in ("src/knos/referee/**", "src/knos/cheats/**", "src/knos/judge.py", "src/knos/self/**", "targets.yml",
                 "CODEOWNERS", ".github/**", "config/**"):
        if need not in (doc.get("core") or []):
            p.append(f"core must hold {need}")
    seen = set()
    for i, t in enumerate(doc.get("targets") or []):
        where = f"targets[{i}]"
        if not isinstance(t, dict):
            p.append(f"{where}: a mapping")
            continue
        tid = t.get("id")
        if not isinstance(tid, str) or not _ID.match(tid):
            p.append(f"{where}.id: lower-case words joined by -")
        elif tid in seen:
            p.append(f"{where}.id {tid} twice")
        seen.add(tid)
        if t.get("kind") not in KINDS:
            p.append(f"{where}.kind: one of {', '.join(KINDS)}")
        if t.get("direction") not in ("lower", "higher"):
            p.append(f"{where}.direction: lower or higher")
        if t.get("status") not in STATUSES:
            p.append(f"{where}.status: one of {', '.join(STATUSES)}")
        if not _USD.match(str(t.get("bounty_usd", ""))):
            p.append(f"{where}.bounty_usd: a decimal string")
        elif _USD.match(str(loop.get("canary_bounty_max_usd", ""))) and float(t["bounty_usd"]) > float(loop["canary_bounty_max_usd"]):
            p.append(f"{where}.bounty_usd: at most loop.canary_bounty_max_usd while the loop pays canary bounties")
        if t.get("kind") == "product":
            for key in ("scope", "public_tests"):
                if not isinstance(t.get(key), list) or not t[key]:
                    p.append(f"{where}.{key}: a list")
            for path in t.get("scope") or []:
                if any(_cheats.matches(path, [g]) for g in doc.get("core") or []):
                    p.append(f"{where}.scope: {path} is trusted core; a product target may not open it to agents")
            if t.get("status") == "open":
                for tier in ("sealed", "audit"):
                    sha = (t.get(tier) or {}).get("sha256")
                    if not isinstance(sha, str) or not _SHA.match(sha):
                        p.append(f"{where}.{tier}.sha256: the sha256 of the hidden bundle")
    return p


def load(root=None) -> dict:
    """targets.yml of the tree `root` (default: the tree this code runs from), validated."""
    root = Path(root) if root is not None else repo_root()
    path = root / TARGETS
    if not path.is_file():
        raise TargetsError([f"no {TARGETS} at {root}"])
    try:
        doc = _read_yaml(path)
    except Exception as why:  # noqa: BLE001 - a file that does not parse is one problem
        raise TargetsError([f"does not parse: {why}"]) from None
    problems = validate(doc)
    if problems:
        raise TargetsError(problems)
    doc["_root"] = str(root)
    return doc


def repo_root() -> Path:
    """The source checkout this code runs from (src/knos/self -> the repository)."""
    return Path(__file__).resolve().parents[3]


def target(cfg: dict, tid: str) -> dict:
    for t in cfg.get("targets") or []:
        if t.get("id") == tid:
            return t
    raise TargetsError([f"no target {tid!r}; targets: {', '.join(t['id'] for t in cfg.get('targets') or [])}"])


# ---- CODEOWNERS ------------------------------------------------------------------------------------------------------

def codeowners_globs(text: str, owner: str | None = None) -> list[str]:
    """The paths of a CODEOWNERS file (those owned by `owner` when given), as the globs targets.yml uses:
    `/dir/` -> `dir/**`, `/file` -> `file`, `*.lock` -> `*.lock` (anywhere)."""
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        pat, owners = parts[0], parts[1:]
        if owner is not None and ("@" + owner.lstrip("@")) not in owners:
            continue
        if pat.startswith("/"):
            pat = pat[1:]
            pat = pat + "**" if pat.endswith("/") else pat
        elif pat.endswith("/"):
            pat = "**/" + pat + "**"
        out.append(pat)
    return out


def codeowners_core(root=None, owner: str | None = None) -> list[str]:
    root = Path(root) if root is not None else repo_root()
    p = root / CODEOWNERS
    return codeowners_globs(p.read_text(encoding="utf-8"), owner) if p.is_file() else []


def core_globs(cfg: dict) -> list[str]:
    """targets.yml's core plus every path CODEOWNERS gives the founder (the union: neither file can open a path)."""
    out = list(cfg.get("core") or [])
    for g in codeowners_core(cfg.get("_root"), cfg.get("founder")):
        if g not in out:
            out.append(g)
    return out


def classify(path: str, cfg: dict, scope=()) -> str:
    path = path.replace("\\", "/").removeprefix("./")
    if _cheats.matches(path, core_globs(cfg)):
        return "core"
    if _cheats.matches(path, list(cfg.get("product") or []) + list(scope or [])):
        return "product"
    return "outside"


def agent_findings(paths, cfg: dict, scope=()) -> list:
    """What an agent's pull request may not change: a core path (refused, `core_path`), or a path outside the product
    (refused, `out_of_scope`)."""
    out = []
    for path in paths:
        kind = classify(path, cfg, scope)
        if kind == "core":
            out.append(_cheats.Finding("self.core_path", "core_path", path, "a trusted-core path: only the founder changes it"))
        elif kind == "outside":
            out.append(_cheats.Finding("self.outside_product", "out_of_scope", path, "not a product path an agent may change"))
    return out
