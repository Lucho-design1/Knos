"""`knos demand "<idea>" --age ... --near ... --price-level ...`: the Qloo demand check from the command line.

One flag per field of knos.qloo_families (the same names as the app's controls, the /mcp tool's arguments and the API's
body, with dashes): --age, --gender, --hide-leader, --exclude, --popularity-max, --near, --radius, --price-level,
--references-brand, --product-kind, --year-min, --year-max, --lookup, --entity-id, ... and --qloo PARAM=VALUE for any other
documented Qloo parameter. It POSTs to the hosted demand check (KNOS_WANTED_URL, default https://knos.onrender.com), where
Qloo is called server side; no Qloo key is needed here. Read-only: nothing is locked or signed.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from . import qloo_families as Q

if TYPE_CHECKING:                                    # typer is imported when the command registers (the CLI's lazy modules)
    import typer

BY_FLAG = {Q.flag(k): k for k in Q.FIELDS}


def parse(args: list[str]) -> dict:
    """--name value / --name=value / --flag (booleans) / --qloo PARAM=VALUE (repeatable), checked against the table."""
    out: dict = {}
    i = 0
    while i < len(args):
        a = args[i]
        if not a.startswith("--"):
            raise ValueError(f"unexpected argument {a!r}: options are --name value (knos demand --help)")
        name, _, val = a.partition("=")
        if name not in BY_FLAG:
            raise ValueError(f"unknown option {name} (knos demand --help lists them)")
        field = BY_FLAG[name]
        kind = Q.FIELDS[field][2]
        if not val and kind == "bool":
            val = "true"
        elif not val:
            i += 1
            if i >= len(args):
                raise ValueError(f"{name} needs a value")
            val = args[i]
        if field == "qloo":
            k, _, v = val.partition("=")
            if not k or not v:
                raise ValueError("--qloo PARAM=VALUE (a parameter docs.qloo.com documents)")
            out.setdefault("qloo", {})[k] = v
        else:
            out[field] = val
        i += 1
    return Q.options(out)


def flags_help() -> str:
    rows = [f"{Q.flag(k)} ({Q.FIELDS[k][0]}): {Q.FIELDS[k][3]} [Qloo {Q.FIELDS[k][1]}]" for k in Q.FIELDS]
    return "\n\n".join(rows)


def ask(idea: str, place: str | None, leader: str | None, opts: dict) -> dict:
    from .demand_tool import TIMEOUT_S, base_url
    url = base_url()
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("KNOS_WANTED_URL must be an https URL (or a local server)")
    body = {"idea": idea, **({"place": place} if place else {}), **({"leader": leader} if leader else {}), **opts}
    req = urllib.request.Request(url + "/api/check", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "knos-cli"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read(4_000_000))
    except urllib.error.HTTPError as e:
        try:
            why = json.loads(e.read(4000) or b"{}").get("error", "")
        except ValueError:
            why = ""
        raise ValueError(f"the demand check said {e.code}: {why or e.reason}") from None


def summary(rep: dict) -> dict:
    fam = rep.get("families") or {}
    return {"report": rep.get("hash"), "verdict": (rep.get("decision") or {}).get("verdict"), "label": rep.get("label"),
            "options": rep.get("options"), "grounding": rep.get("grounding"),
            "families": {f: {k: v for k, v in a.items() if k in ("question", "call", "answer", "hot", "by_id", "places", "brand_id")}
                         for f, a in fam.items()},
            "calls": len(rep.get("calls") or [])}


def register(app, help_lines: list | None = None) -> None:
    """`knos demand "<idea>" [--flags]` on the main app. `help_lines`: cli._HELP."""
    import importlib
    globals()["typer"] = importlib.import_module("typer")   # the annotations below are strings (postponed); Typer resolves them here

    if help_lines is not None:
        help_lines.append(("demand", "Demand", "Is it wanted? Qloo's demand check with every family's option as a flag."))

    @app.command("demand", context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
                 help="Qloo demand check: who, gaps, where, price tier, who serves it, media kind, look up.\n\n" + flags_help())
    def demand_(ctx: typer.Context,
                idea: str = typer.Argument(..., help="the product idea in plain words (8 to 500 characters)"),
                place: str = typer.Option("", "--place", help="the launch market (city or country)"),
                leader: str = typer.Option("", "--leader", help="the market leader to compare against"),
                as_json: bool = typer.Option(False, "--json", help="the whole report, not the summary")) -> None:
        try:
            opts = parse(list(ctx.args))
            rep = ask(idea, place or None, leader or None, opts)
        except ValueError as why:
            typer.echo(str(why), err=True)
            raise typer.Exit(2) from None
        typer.echo(json.dumps(rep if as_json else summary(rep), indent=1, ensure_ascii=False, default=str))
