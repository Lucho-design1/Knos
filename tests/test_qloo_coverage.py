"""docs/reference/QLOO-COVERAGE.md is what scripts/qloo_coverage.py writes from the docs tables and the one table of names."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_qloo_coverage_matches_the_tables():
    spec = importlib.util.spec_from_file_location("qloo_coverage", ROOT / "scripts" / "qloo_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = mod.render()
    assert (ROOT / "docs" / "reference" / "QLOO-COVERAGE.md").read_text(encoding="utf-8") == text, "run python scripts/qloo_coverage.py"
    rows = [line for line in text.splitlines() if line.startswith("| `")]
    assert len(rows) > 500 and all(("| USED |" in r) or ("| N/A |" in r and "Qloo" in r) for r in rows)
