"""Rules the repository keeps: Qloo data never committed, MOCK labelled, the framing stated, the Qloo part explained."""
from pathlib import Path

from knos_wanted import mock
from knos_wanted.qloo import ENDPOINTS, MOCK_LABEL, Qloo

ROOT = Path(__file__).resolve().parents[1]


def test_cache_and_probe_are_git_ignored():
    ignored = (ROOT / ".gitignore").read_text().split()
    assert ".cache/" in ignored and "probe.json" in ignored and ".env" in ignored


def test_readme_states_framing_and_qloo_part():
    text = (ROOT / "README.md").read_text()
    assert "Directional demand evidence, not a sales forecast." in text
    assert "## What is Qloo-powered" in text
    assert "MOCK (synthetic, not real Qloo data)" in text
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")


def test_every_mock_answer_is_labelled():
    q = Qloo()
    for name in ENDPOINTS:
        assert q.get(name, {"query": "x", "filter.query": "x", "signal.interests.tags": "t"})["_mock"] == MOCK_LABEL


def test_mock_names_are_marked_synthetic():
    body = mock.respond("insights", {"filter.type": "urn:entity:brand", "signal.interests.tags": "t"})
    assert all("(synthetic)" in e["name"] for e in body["results"]["entities"])


def test_no_recorded_qloo_bodies_in_repo():
    for p in ROOT.rglob("*.json"):
        if ".cache" in p.parts or ".venv" in p.parts:
            continue
        raise AssertionError(f"unexpected JSON file in the repository: {p.relative_to(ROOT)}")
