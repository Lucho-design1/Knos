"""scripts/truth_check.py's fee rule reads the one fee config (config/fees.yaml) beside the two builds of knos_pay: a
decided fee and the part of it invoiced off chain pass, a rate no line sets is still found. And a Knos release named
beside a program ("knos_pay 0.3.34") is not read as the program's build."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FEES = """version: 1
fees:
  payout:
    status: "live"
    rate_bps: 30
  bounty_platform:
    status: "decided"
    rate_bps: 500
    onchain_line: "payout"
  free_line:
    status: "proposed"
    rate_bps: 0
"""


def _tool():
    spec = importlib.util.spec_from_file_location("truth_check_fees_tool", ROOT / "scripts" / "truth_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod                      # dataclasses look their module up by name
    spec.loader.exec_module(mod)
    return mod


def _root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "fees.yaml").write_text(FEES, encoding="utf-8")
    pay = tmp_path / "src" / "knos" / "settle" / "v2"
    pay.mkdir(parents=True)
    (pay / "pay.py").write_text("FEE_BPS, FEE_MIN, MIN_AMOUNT = 25, 50_000, 1_000_000\n", encoding="utf-8")
    return tmp_path


def test_the_one_fee_config_and_a_row_of_constants_give_the_rates(tmp_path):
    assert _tool().fee_rates(_root(tmp_path)) == {"0.25", "0.30", "5.00", "4.70"}      # no 0%: a free line is no rate


def test_a_decided_fee_passes_and_a_rate_no_line_sets_is_found(tmp_path):
    tool = _tool()
    rates = tool.fee_rates(_root(tmp_path))
    said = [tool.Statement("docs/MONEY.md", 1, "The bounty fee 5% is a starting price."),
            tool.Statement("docs/MONEY.md", 2, "The rest, the bounty fee's off-chain 4.70%, is invoiced."),
            tool.Statement("docs/MONEY.md", 3, "A lab order fee 7% is charged.")]
    assert [(p.rule, p.line) for p in tool.price_problems(said, {}, rates)] == [("fee", 3)]


def test_a_release_named_beside_a_program_is_not_its_build():
    tool = _tool()
    data = {"programs": {"knos_pay": {"on_chain": "2.2"}}}
    said = [tool.Statement("docs/reference/AGENTS.md", 1, "Shown on devnet: V34PAY's knos_pay 0.3.34 test program is live there."),
            tool.Statement("docs/reference/AGENTS.md", 2, "Shown on devnet: knos_pay 2.1 is live there.")]
    assert [(p.rule, p.line) for p in tool.version_problems(said, data)] == [("version", 2)]
