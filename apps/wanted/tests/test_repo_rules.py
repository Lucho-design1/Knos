"""Rules the repository keeps: Qloo data never committed, MOCK labelled, the framing stated, the Qloo part explained,
the key never in code, Qloo reached only through its MCP server."""
import re
from pathlib import Path

from knos_wanted import mock_mcp
from knos_wanted.qloo_mcp import MOCK_LABEL, InProcess, Qloo

ROOT = Path(__file__).resolve().parents[1]


def test_cache_and_probe_are_git_ignored():
    ignored = (ROOT / ".gitignore").read_text().split()
    assert ".cache/" in ignored and "probe.json" in ignored and ".env" in ignored and "node_modules/" in ignored


def test_readme_states_framing_and_qloo_part():
    text = (ROOT / "README.md").read_text()
    assert "Directional demand evidence, not a sales forecast." in text
    assert "aggregate taste, not a prediction about one person" in text
    assert "## What is Qloo-powered" in text
    assert "MOCK (synthetic, not real Qloo data)" in text
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")


def test_every_mock_answer_is_labelled():
    q = Qloo(InProcess(), mode="mock")
    assert q.label == MOCK_LABEL
    for name in mock_mcp.TOOLS:
        if name != "qloo_capabilities":
            assert mock_mcp.call(name, {})["_mock"] == MOCK_LABEL


def test_mock_names_are_marked_synthetic():
    body = mock_mcp.call("qloo_recommend", {"target_type": "brand", "signals": ["mock-brand-x-a"]})
    assert all("(synthetic)" in e["name"] for e in body["results"])


def test_no_recorded_qloo_bodies_in_repo():
    for p in ROOT.rglob("*.json"):
        if ".cache" in p.parts or ".venv" in p.parts or "node_modules" in p.parts:
            continue
        raise AssertionError(f"unexpected JSON file in the repository: {p.relative_to(ROOT)}")


def test_qloo_only_through_mcp_and_no_key_in_code():
    code = "\n".join(p.read_text() for p in (ROOT / "knos_wanted").rglob("*.py")) + (ROOT / "bridge" / "qloo_bridge.mjs").read_text()
    assert "hackathon.api.qloo.com" not in code          # no direct REST calls: the harness owns the endpoint
    assert "X-Api-Key" not in code
    assert not re.search(r"QLOO_API_KEY\s*=", code)
    js = (ROOT / "knos_wanted" / "static" / "app.js").read_text()
    assert "qloo.com" not in js and "QLOO" not in js          # the browser never talks to Qloo
