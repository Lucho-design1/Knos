"""docs/reference/SIBYL-COVERAGE.md is what scripts/sibyl_coverage.py writes: every row's file still holds its code, every
N/A has the source's reason, and the 8 MCP tools and the CLI's subcommands each have a row."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = "init upgrade claim email status whoami devices dashboard logout health memory update setup migrate save debloat skills autosave refresh reminders hook"
MCP = "memory_remember memory_recall memory_search memory_list memory_forget memory_set_state memory_get_state memory_record_event"


def test_sibyl_coverage_matches_the_code():
    spec = importlib.util.spec_from_file_location("sibyl_coverage", ROOT / "scripts" / "sibyl_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.problems(mod.ROWS) == []
    assert (ROOT / "docs" / "reference" / "SIBYL-COVERAGE.md").read_text(encoding="utf-8") == mod.render(), "run python scripts/sibyl_coverage.py"
    caps = " ".join(r["cap"] for r in mod.ROWS)
    assert all(f"sibyl {c}" in caps for c in CLI.split()) and all(f"MCP {t}" in caps for t in MCP.split())
    assert all(r["reason"] for r in mod.ROWS if r["status"] == "N/A")
