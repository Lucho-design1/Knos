"""SIBYL-COVERAGE.md: every capability of Sibyl Memory's free plan on 22 Oct 2026 -> USED (the file, and where a person
meets it on Knos's five interfaces) or N/A (the source's own reason). Pro-only features are N/A on Free, as the source says.

Sources, read 22 Oct 2026: docs.sibyllabs.org/memory/ (install, concepts, cli, integrations, before-accounts, tiers), the
installed CLI's own help (`sibyl --help` in Ubuntu-22.04: cli 0.5.0, client 0.9.0, mcp 0.3.0, hermes 0.5.0), the MCP
server's tools/list (sibyl-memory 1.30.0), and the SDK Knos pins (sibyl-memory-client 0.8.1, the last that runs without an
account: the server stays account-free until the founder chooses Pro or staking).

  python scripts/sibyl_coverage.py           write docs/reference/SIBYL-COVERAGE.md
  python scripts/sibyl_coverage.py --check   exit 1 when the file is not what this table and the code say (CI)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "reference" / "SIBYL-COVERAGE.md"
D = "https://docs.sibyllabs.org/memory"
H = "src/knos/proof/history.py"
SK = ".claude/skills/knos-goal/SKILL.md"
CROSS = dict(app="a crossing's 'memory' steps (the agent recalls the paper first)", mcp="`knos_memory_recall`, `knos_memory_search`",
             api="`GET /api/memory/search`")
PROOF = dict(cli="`knos proof` (check, gate, lint, learn, record) and the Stop hook `knos hook proof`")


def u(cap, group, code, source, app="—", front="—", mcp="—", api="—", cli="—"):
    return {"cap": cap, "group": group, "status": "USED", "code": code, "source": source, "app": app, "front": front, "mcp": mcp, "api": api, "cli": cli}


def na(cap, group, reason, source):
    return {"cap": cap, "group": group, "status": "N/A", "code": "", "source": source, "reason": reason}


PRO = "the source (tiers): Pro only, 'Pro removes the cap, adds computers, and makes save, debloat and skill extraction run for you, with self-learning and the linter'"
ROWS = [
    # ---- the five tiers + search (docs/memory/concepts) and the SDK calls behind them
    u("HOT state: set_state / get_state", "Memory model", f"{H}::.get_state(", f"{D}/concepts", **CROSS, **PROOF),
    u("WARM entities: set_entity / get_entity / list_entities", "Memory model", f"{H}::set_entity", f"{D}/concepts", **CROSS, **PROOF),
    u("COLD journal: write_event / read_events", "Memory model", f"{H}::read_events", f"{D}/concepts", **CROSS, **PROOF),
    u("REFERENCE: set_reference / get_reference", "Memory model", "src/knos/record/journal.py::set_reference", f"{D}/concepts",
      app="the paper on the reference shelf (crossing step)", mcp="`knos_memory_search`", api="`GET /api/memory/search`", cli="`knos record`"),
    u("ARCHIVE: archive_entity (recoverable forget)", "Memory model", f"{H}::archive_entity", f"{D}/concepts", **PROOF),
    na("delete_entity (permanent hard delete)", "Memory model", "the source: 'a permanent hard delete'; Knos archives (recoverable) and never hard-deletes a record", f"{D}/concepts"),
    u("FTS5 search: search / search_entities", "Memory model", "src/knos/record/search.py::verdicts", f"{D}/concepts", **CROSS, **PROOF),
    u("Search verdicts: refine_zero (why nothing was found)", "Memory model", "src/knos/record/search.py::refine_zero", f"{D}/concepts",
      mcp="`knos_memory_search`", api="`GET /api/memory/search` (verdict)"),
    u("Multi-tenant: set_tenant (one tenant per repo)", "Memory model", "src/knos/store.py::set_tenant", f"{D}/concepts", **PROOF),
    u("Single source of truth: UNIQUE (tenant, category, name), ConflictError", "Memory model", f"{H}::set_entity", f"{D}/concepts",
      app="two agents on one crossing: the second is refused (agent.py, 'another agent holds this crossing')", **PROOF),
    u("Free-tier cap: 5 MB (FREE_TIER_CAP_BYTES, CapGate, free_tier_status)", "Free plan", "src/knos/store.py::CapGate", f"{D}/tiers",
      api="`GET /api/memory/search` (store size)", cli="each goal's report: DB size against 5,242,880 bytes (`sibyl status`)"),
    u("One computer on Free", "Free plan", f"{SK}::sibyl status", f"{D}/tiers", cli="`sibyl devices` / `sibyl status` on the founder's PC (one device)"),
    u("Account required on every plan (sibyl init)", "Free plan", "src/knos/store.py::sibyl init", f"{D}/before-accounts",
      cli="the founder's PC is signed in (WSL); the server keeps the account-free client 0.8.1 pinned (<0.9)"),
    u("Save procedure (manual, with reminders)", "Free plan", f"{SK}::/sibyl-save", f"{D}/tiers", cli="every goal ends with `/sibyl-save` (Claude Code)"),
    u("Debloat procedure (manual, with reminders)", "Free plan", f"{SK}::/sibyl-debloat", f"{D}/tiers", cli="every goal ends with `/sibyl-debloat`"),
    # ---- the installed CLI's own subcommands (sibyl --help, cli 0.5.0)
    u("sibyl init", "CLI", "src/knos/store.py::sibyl init", f"{D}/cli", cli="signed in once on the founder's PC (Knos never prompts a user to run it)"),
    u("sibyl status", "CLI", f"{SK}::sibyl status", f"{D}/cli", cli="the DB size line in every goal's report"),
    u("sibyl whoami", "CLI", "scripts/sibyl_coverage.py::sibyl whoami", f"{D}/cli", cli="the live proof of this coverage (masked one-line summary)"),
    u("sibyl devices", "CLI", "scripts/sibyl_coverage.py::sibyl devices", f"{D}/cli", cli="the live proof: one computer, the Free limit"),
    u("sibyl health", "CLI", "scripts/sibyl_coverage.py::sibyl health", f"{D}/cli", cli="the live proof: the provider self-check"),
    u("sibyl memory list / search / recall", "CLI", "scripts/sibyl_coverage.py::sibyl memory search", f"{D}/cli", cli="the live proof: reads the store the goals saved"),
    u("sibyl update", "CLI", "scripts/sibyl_coverage.py::sibyl update", f"{D}/cli", cli="the live proof: newer releases checked (never --apply: 0.9 needs an account on the server)"),
    u("sibyl refresh", "CLI", "scripts/sibyl_coverage.py::sibyl refresh", f"{D}/cli", cli="the live proof: plan checked now (Free)"),
    u("sibyl reminders", "CLI", "scripts/sibyl_coverage.py::sibyl reminders", f"{D}/cli", cli="save and debloat reminders on (Free)"),
    u("sibyl skills", "CLI", "scripts/sibyl_coverage.py::sibyl skills", f"{D}/cli", cli="the live proof: the save and debloat procedures installed"),
    u("sibyl save (one fact now)", "CLI", f"{SK}::/sibyl-save", f"{D}/cli", cli="`/sibyl-save` at the end of every goal"),
    u("sibyl debloat (measure, plan)", "CLI", f"{SK}::/sibyl-debloat", f"{D}/cli", cli="`/sibyl-debloat` at the end of every goal"),
    na("sibyl setup", "CLI", "the source: 'Refuses on native Windows on the same terms as sibyl init'; Claude Code runs natively here, so its MCP entry starts Sibyl's server in WSL by hand", f"{D}/cli"),
    na("sibyl hook", "CLI", "the CLI's own help: 'installed by sibyl setup; not for manual use', and setup does not run on native Windows", f"{D}/cli"),
    na("sibyl migrate", "CLI", "the source: 'guided, backup-first onboarding of your existing agent memory'; Knos's memory has always been in Sibyl, nothing to migrate", f"{D}/cli"),
    na("sibyl upgrade / sibyl claim", "CLI", "the source: the Pro billing flow (card, USDC on Base, or staking $SIBYL); the free plan only", f"{D}/tiers"),
    na("sibyl email", "CLI", "the source: the account's email for receipts and notices; Knos stores no account email", f"{D}/cli"),
    na("sibyl dashboard", "CLI", "the source: opens the account page in a browser; nothing an agent or Knos needs", f"{D}/cli"),
    na("sibyl logout", "CLI", "the source: removes local credentials; the founder's PC stays signed in", f"{D}/cli"),
    na("sibyl autosave", "CLI", PRO, f"{D}/tiers"),
    # ---- the MCP server's tools/list (sibyl-memory 1.30.0): Claude Code's own memory while it builds Knos
    *[u(f"MCP {t}", "MCP", f"{SK}::{t}", f"{D}/integrations", cli=f"Claude Code's Sibyl MCP `{t}` while it works on Knos (the knos-goal skill)")
      for t in ("memory_remember", "memory_recall", "memory_search", "memory_list", "memory_set_state", "memory_get_state", "memory_record_event")],
    na("MCP memory_forget", "MCP", "the source pairs forget with archive or a hard delete; Knos's records are never forgotten from an agent", f"{D}/integrations"),
    # ---- integrations (docs/memory/integrations)
    u("SDK directly (MemoryClient)", "Integrations", "src/knos/store.py::MemoryClient", f"{D}/integrations", **CROSS, **PROOF),
    na("Hermes provider", "Integrations", "the source: the memory provider for Hermes Agent v0.13+; Knos ships Hermes skills (hermes/), and which memory a Hermes user runs is theirs", f"{D}/integrations"),
    na("LangGraph store", "Integrations", "the source: a LangGraph BaseStore; Knos's agents are not LangGraph graphs", f"{D}/integrations"),
    # ---- Pro only: N/A on Free (docs/memory/tiers)
    na("Cap removed", "Pro", PRO, f"{D}/tiers"),
    na("Up to 10 computers", "Pro", PRO, f"{D}/tiers"),
    na("Self-learning (MemoryClient.learn)", "Pro", PRO + "; knos.proof.history calls learn() when an account has it and carries on without", f"{D}/tiers"),
    na("Memory linter (MemoryClient.lint)", "Pro", PRO + "; Knos's own proof lint runs instead", f"{D}/tiers"),
    na("Automatic save (about every hour)", "Pro", PRO, f"{D}/tiers"),
    na("Automatic debloat", "Pro", PRO, f"{D}/tiers"),
    na("Skill proposals (list / accept / reject)", "Pro", PRO, f"{D}/tiers"),
    na("Session capsule save", "Pro", "the CLI's own help: 'a session capsule (Pro)'", f"{D}/cli"),
    na("Sovereign", "Pro", "the source: in development, not offered", "https://docs.sibyllabs.org/"),
    na("Teams (3 to 200 Pro seats on one bill)", "Pro", "the source: paid seats of Pro, not the free plan", f"{D}/teams"),
]


def problems(rows) -> list[str]:
    bad = []
    for r in rows:
        if r["status"] == "USED":
            path, _, needle = r["code"].partition("::")
            f = ROOT / path
            if not f.exists() or needle not in f.read_text(encoding="utf-8", errors="replace"):
                bad.append(f"{r['cap']}: {path} does not contain {needle!r}")
    return bad


def render() -> str:
    used = sum(r["status"] == "USED" for r in ROWS)
    out = ["# Sibyl Memory coverage (free plan)", "",
           "Every capability of Sibyl Memory's free plan on 22 Oct 2026, one row each: USED (the file, and where a person meets it on",
           "the app, the front door, the hosted /mcp, the API and the `knos` CLI) or N/A with the source's own reason; Pro-only features",
           "are N/A on Free.", "", "Written by `scripts/sibyl_coverage.py`; `--check` fails CI when a row's file no longer holds its code.", "",
           f"{len(ROWS)} rows: {used} USED, {len(ROWS) - used} N/A. Installed on the founder's PC: sibyl cli 0.5.0, client 0.9.0, mcp 0.3.0,",
           "hermes 0.5.0 (MCP server sibyl-memory 1.30.0, 8 tools). The Knos server pins sibyl-memory-client 0.8.1 (0.9 needs an account).", "",
           "| Capability | Group | Status | Code | App | Front door | /mcp | API | CLI | Source |", "|---|---|---|---|---|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "\\|")  # noqa: E731
    for r in ROWS:
        if r["status"] == "USED":
            out.append(f"| {esc(r['cap'])} | {r['group']} | USED | `{r['code'].partition('::')[0]}` | {esc(r['app'])} | {esc(r['front'])} | "
                       f"{esc(r['mcp'])} | {esc(r['api'])} | {esc(r['cli'])} | {r['source']} |")
        else:
            out.append(f"| {esc(r['cap'])} | {r['group']} | N/A | — | {esc(r['reason'])} | | | | | {r['source']} |")
    return "\n".join(out) + "\n"


# the live proof of the CLI rows: run in the WSL distro where Sibyl is signed in, read-only commands only
LIVE = ["sibyl whoami", "sibyl devices", "sibyl health", "sibyl status", "sibyl memory search knos", "sibyl update", "sibyl refresh",
        "sibyl reminders", "sibyl skills"]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    bad = problems(ROWS)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    text = render()
    if "--check" in argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("SIBYL-COVERAGE.md matches the code" if ok else "SIBYL-COVERAGE.md differs: run python scripts/sibyl_coverage.py")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {text.count('| USED |')} USED, {text.count('| N/A |')} N/A")
    return 0


if __name__ == "__main__":
    sys.exit(main())
