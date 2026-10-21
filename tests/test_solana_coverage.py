"""docs/reference/SOLANA-COVERAGE.md is what scripts/solana_coverage.py writes: every documented RPC method and Token-2022
extension has a row, and every USED row's file still holds its code."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("solana_coverage", ROOT / "scripts" / "solana_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_solana_coverage_matches_the_code():
    mod = _mod()
    rows = mod.rpc_rows() + mod.ROWS
    assert mod.problems(rows) == []
    assert (ROOT / "docs" / "reference" / "SOLANA-COVERAGE.md").read_text(encoding="utf-8") == mod.render(), "run python scripts/solana_coverage.py"
    caps = {r["cap"] for r in rows}
    assert len(mod.HTTP) == 53 and len(mod.WS) == 18 and set(mod.HTTP + mod.WS) <= caps
    assert all(r["status"] == "USED" for r in rows if r["group"].startswith("RPC"))          # every RPC method is sent by Knos code
    from knos.platform import token22
    assert set(token22.NAMES.values()) <= caps                                                # every Token-2022 extension has a row
    assert all(r["reason"] for r in rows if r["status"] == "N/A")
