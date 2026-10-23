"""`knos taskpack export | verify | grade | rows`: a maintainer's merged issue + pull request as a sealed task package."""
from __future__ import annotations

import json
import os
import re
import shlex
import urllib.request
from pathlib import Path

from . import atropos, export as ex, grade as gr

_REF = re.compile(r"^([\w.-]{1,100}/[\w.-]{1,100})#(\d{1,9})$")
_CLOSES = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)")


def github(path: str, env: dict | None = None) -> dict:
    env = dict(os.environ) if env is None else env
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json", "User-Agent": "knos-taskpack"})
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - api.github.com only
        return json.load(r)


def from_github(ref: str, fetch=github) -> tuple[dict, str, dict]:
    """(pr, merge commit, issue) of a merged pull request, from GitHub's API."""
    got = _REF.match(ref)
    if not got:
        raise ex.Refused("name the pull request as owner/repo#number")
    repo, number = got.group(1), int(got.group(2))
    pr = fetch(f"repos/{repo}/pulls/{number}")
    if not pr.get("merged_at") or not pr.get("merge_commit_sha"):
        raise ex.Refused(f"{ref} is not merged: only a merged fix becomes a task")
    closes = _CLOSES.search(pr.get("body") or "")
    issue = {"number": None, "title": pr.get("title") or "", "body": pr.get("body") or ""}
    if closes:
        i = fetch(f"repos/{repo}/issues/{closes.group(1)}")
        issue = {"number": int(closes.group(1)), "title": i.get("title") or "", "body": i.get("body") or ""}
    return {"repo": repo, "number": number}, pr["merge_commit_sha"], issue


def register(app, help_lines: list | None = None) -> None:
    import typer

    if help_lines is not None:
        help_lines.append(("taskpack", "For money", "A merged issue + pull request as a sealed, verified task package (maintainer opt-in)."))
    group = typer.Typer(help="Task packages: a merged fix's hidden tests sealed, with the issue, scope, judge and cheat rules (docs/reference/TASK_PACKAGES.md).", no_args_is_help=True)
    app.add_typer(group, name="taskpack")

    @group.command("export")
    def export_cmd(ref: str = typer.Argument(..., help="owner/repo#<merged pull request>"),
                   repo_dir: Path = typer.Option(..., "--repo-dir", help="a local clone of the repository (read only: nothing in it changes)"),
                   out: Path = typer.Option(Path("taskpacks"), "--out", help="the folder the package is written into"),
                   opt_in: bool = typer.Option(False, "--opt-in", help="you are the maintainer and opt this task in (else .knos/taskpack.yml `export: true` must be in the repository)"),
                   who: str = typer.Option("", "--maintainer", help="your GitHub login, recorded with --opt-in"),
                   merge: str = typer.Option("", "--merge", help="the merge commit (offline; with --issue-title/--issue-body)"),
                   issue_number: int = typer.Option(0, "--issue"),
                   issue_title: str = typer.Option("", "--issue-title"),
                   issue_body: str = typer.Option("", "--issue-body"),
                   test_cmd: str = typer.Option("", "--test-cmd", help="the command that runs the hidden tests; {tests} is their paths, {python} this Python"),
                   encrypt: bool = typer.Option(False, "--encrypt", help="encrypt the sealed files; the key is written beside the package (<out>/<task id>.key), never inside it, and never printed"),
                   price: int = typer.Option(-1, "--price", help="a sale price in millionths of USDC, to show the fee split")) -> None:
        """Export a merged pull request and its issue as a sealed task package, after checking that its tests fail before the fix and pass after it."""
        try:
            if merge:
                got = _REF.match(ref)
                if not got:
                    raise ex.Refused("name the pull request as owner/repo#number")
                pr, sha, issue = {"repo": got.group(1), "number": int(got.group(2))}, merge, {"number": issue_number or None, "title": issue_title, "body": issue_body}
            else:
                pr, sha, issue = from_github(ref)
            folder = ex.export(repo_dir, merge=sha, pr=pr, issue=issue, out=out, opt_in_flag=opt_in, who=who,
                               test_cmd=shlex.split(test_cmd) if test_cmd else None, encrypt=encrypt, price_units=price if price >= 0 else None)
        except (ex.Refused, OSError) as why:
            typer.echo(f"Not exported: {why}", err=True)
            raise typer.Exit(1) from None
        m = ex.load(folder)
        typer.echo(f"Wrote {folder}: {m['task_id']}, spec sha256 {m['spec_sha256']}. {m['sealed']['tests_count']} hidden test file(s) sealed; "
                   f"they fail before the fix ({m['verified']['base_summary']}) and pass after it ({m['verified']['merge_summary']}).")
        typer.echo(f"Licence: {m['licence']['why']}. Fee: {m['fee']['status']}.")

    @group.command("verify")
    def verify_cmd(pack: Path = typer.Argument(...), key_file: Path = typer.Option(None, "--key")) -> None:
        """Check a package: its spec hash and each sealed file's hash."""
        wrong = ex.verify(pack, ex.key_of(pack, key_file))
        for w in wrong:
            typer.echo(f"  - {w}")
        typer.echo("The package checks." if not wrong else "The package does not check.")
        raise typer.Exit(1 if wrong else 0)

    @group.command("grade")
    def grade_cmd(pack: Path = typer.Argument(...), patch: Path = typer.Option(..., "--patch"),
                  repo_dir: Path = typer.Option(..., "--repo-dir"), key_file: Path = typer.Option(None, "--key")) -> None:
        """Grade a candidate patch: cheat rules, then the hidden tests. Prints counts and rules only. The candidate's code runs on this machine, unsandboxed: grade untrusted patches in a disposable container."""
        try:
            got = gr.grade(pack, repo_dir, patch.read_text(encoding="utf-8"), key=ex.key_of(pack, key_file))
        except ex.Refused as why:
            typer.echo(str(why), err=True)
            raise typer.Exit(2) from None
        typer.echo(json.dumps(got, indent=1))
        raise typer.Exit(0 if got["passed"] else 1)

    @group.command("rows")
    def rows_cmd(packs: list[Path] = typer.Argument(...), out: Path = typer.Option(Path("tasks.jsonl"), "--out")) -> None:
        """Training-environment rows (Atropos), one per package: what the solver may see and the sealed hashes."""
        n = atropos.write_jsonl(packs, out)
        typer.echo(f"Wrote {out}: {n} row(s).")
