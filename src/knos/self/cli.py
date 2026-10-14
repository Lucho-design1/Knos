"""`knos self ...` (also `python -m knos.self ...`): Knos builds Knos.

    knos self targets [--root DIR]                      the targets, validated, and the core/product split
    knos self check-pr DIFF [--target ID]               what an agent's pull request may not change (CI on forked PRs)
    knos self seal DIR                                  a hidden bundle's sha256 (for targets.yml) and its .tgz
    knos self init REPO STATE [--main main]             the trusted referee checkout and version v0
    knos self parent REPO STATE TARGET                  the version agents build on next (HGM)
    knos self run REPO STATE TARGET CANDIDATE [--parent V] [--agent NAME] [--claimed-metric N] [--pay-wallet DIR --payee ADDR --mint MINT]
    knos self audit REPO STATE TARGET [--rollback]      the audit tier on accepted versions
    knos self rollback REPO STATE VERSION               one command: the version leaves the loop branch
    knos self referee REPO STATE CANDIDATE [--approval FILE]   a referee change: red-team gate, shadow, founder signature
    knos self archive STATE                             the archive (versions, lineage, decisions)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="knos self", description="Knos builds Knos: safe recursive self-improvement (docs/reference/SELF.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("targets")
    s.add_argument("--root", default=None)
    s = sub.add_parser("check-pr")
    s.add_argument("diff")
    s.add_argument("--target", default=None)
    s.add_argument("--root", default=None)
    s = sub.add_parser("seal")
    s.add_argument("dir")
    s.add_argument("--out", default=None)
    for name in ("init", "parent", "run", "audit", "rollback", "referee"):
        s = sub.add_parser(name)
        s.add_argument("repo")
        s.add_argument("state")
        s.add_argument("--branch", default=None, help="the local loop branch (default: targets.yml loop.branch)")
        if name == "init":
            s.add_argument("--main", default="main")
        if name in ("parent", "run", "audit"):
            s.add_argument("target")
        if name in ("run", "referee"):
            s.add_argument("candidate")
        if name == "rollback":
            s.add_argument("version")
            s.add_argument("--reason", default="rolled back by the founder")
        if name == "run":
            s.add_argument("--parent", default=None)
            s.add_argument("--agent", default="")
            s.add_argument("--note", default="")
            s.add_argument("--claimed-metric", type=float, default=None)
            s.add_argument("--pay-wallet", default=None)
            s.add_argument("--payee", default=None)
            s.add_argument("--mint", default=None)
            s.add_argument("--sandbox", default="auto")
        if name == "audit":
            s.add_argument("--rollback", action="store_true")
        if name == "referee":
            s.add_argument("--approval", default=None)
            s.add_argument("--cases", default=None, help="comma-separated red-team case ids (default: all)")
    s = sub.add_parser("archive")
    s.add_argument("state")
    a = ap.parse_args(argv)

    from . import config
    if a.cmd == "targets":
        cfg = config.load(a.root)
        _print({"founder": cfg["founder"], "loop": cfg["loop"], "core": config.core_globs(cfg), "product": cfg["product"],
                "targets": [{k: t.get(k) for k in ("id", "kind", "status", "direction", "bounty_usd", "what")} for t in cfg["targets"]]})
        return 0
    if a.cmd == "check-pr":
        from .. import cheats
        cfg = config.load(a.root)
        diff = Path(a.diff).read_text(encoding="utf-8", errors="replace")
        scope = config.target(cfg, a.target).get("scope") or () if a.target else ()
        paths = sorted({f.path for f in cheats.parse_diff(diff)})
        found = config.agent_findings(paths, cfg, scope) + cheats.scan_diff(diff, scope=tuple(scope), core=tuple(config.core_globs(cfg)))
        refused = cheats.refused(found)
        _print({"refused": refused, "findings": [f.to_dict() for f in found]})
        return 1 if refused else 0
    if a.cmd == "seal":
        from . import tiers
        data = tiers.pack(a.dir)
        out = Path(a.out or (Path(a.dir).name + ".tgz"))
        out.write_bytes(data)
        _print({"sha256": tiers.bundle_sha(data), "file": str(out), "bytes": len(data)})
        return 0
    if a.cmd == "archive":
        from .archive import Archive
        _print(Archive(Path(a.state) / "archive.json").data)
        return 0
    from .loop import Loop
    lp = Loop(a.repo, a.state, branch=a.branch)
    if a.cmd == "init":
        _print(lp.init(a.main))
    elif a.cmd == "parent":
        _print(lp.parent(a.target))
    elif a.cmd == "run":
        pay = None
        if a.pay_wallet:
            if not (a.payee and a.mint):
                print("--pay-wallet needs --payee and --mint", file=sys.stderr)
                return 2
            pay = {"wallet_dir": a.pay_wallet, "payee": a.payee, "mint": a.mint}
        got = lp.run(a.target, a.candidate, parent=a.parent, agent=a.agent, claimed_metric=a.claimed_metric, pay=pay,
                     sandbox=a.sandbox, note=a.note)
        _print({"node": got["node"], "choice": got["choice"], "payout": got["payout"], "record_lines": got["record_lines"]})
        return 0 if got["node"]["decision"] == "canary" else 1
    elif a.cmd == "audit":
        _print(lp.audit(a.target, rollback=a.rollback))
    elif a.cmd == "rollback":
        _print(lp.rollback(a.version, reason=a.reason))
    elif a.cmd == "referee":
        approval = json.loads(Path(a.approval).read_text(encoding="utf-8")) if a.approval else None
        cases = None
        if a.cases:
            from .. import cheats
            want = set(a.cases.split(","))
            cases = [c for c in cheats.CASES if c.id in want]
        got = lp.referee(a.candidate, approval=approval, cases=cases)
        _print(got)
        return 0 if got["decision"] == "approved" else 1
    return 0


def register(app, help_lines: list | None = None) -> None:
    """`knos self` in the knos command (src/knos/cli.py _MODULES row)."""
    import importlib
    typer = importlib.import_module("typer")
    globals()["typer"] = typer      # the command's `ctx: typer.Context` is a string annotation read from this module
    if help_lines is not None:
        help_lines.append(("self", "For a repository's workflows", "Knos builds Knos: agents improve product code, judged by the referee from main, paid on devnet."))

    @app.command("self", context_settings={"allow_extra_args": True, "ignore_unknown_options": True, "help_option_names": []})
    def self_(ctx: typer.Context) -> None:
        """Knos builds Knos: targets, the loop, the archive, audits, rollback, referee changes (docs/reference/SELF.md)."""
        raise typer.Exit(main(list(ctx.args) or ["--help"]))
