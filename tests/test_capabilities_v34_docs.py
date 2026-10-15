"""The stale blockhash fact is gone from the pages that said it, the new pages name their sources and tests, and the
Agent Card file is where A2A looks for one. Reads files only."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "docs" / "reference"
NEW = ["DURABLE_NONCES.md", "X402_UPTO.md", "SAS_INPUTS.md", "SPENDING_LIMITS.md", "KORA_CCTP.md", "A2A.md", "CLAUDE_AGENTS.md"]


def test_no_page_says_a_blockhash_lives_a_minute_any_more():
    for name in ("ALPENGLOW.md", "ADVANCE.md"):
        text = (REF / name).read_text(encoding="utf-8")
        for sentence in re.split(r"(?<=[.:;])\s", text):
            if "blockhash" in sentence.lower():
                assert not re.search(r"\b60 s\b|about a minute|60 to 90", sentence), (name, sentence)
        assert "33 s" in text and "DURABLE_NONCES.md" in text


def test_each_new_page_cites_its_sources_and_its_tests():
    for name in NEW:
        text = (REF / name).read_text(encoding="utf-8")
        assert "14 Oct 2026" in text and "https://" in text, name
        for t in re.findall(r"`(tests/test_[a-z0-9_]+\.py)`", text):
            assert (ROOT / t).is_file(), (name, t)


def test_the_agent_card_is_at_the_well_known_path():
    card = json.loads((ROOT / "examples" / "a2a" / ".well-known" / "agent-card.json").read_text(encoding="utf-8"))
    assert "Knos" in card["name"] and card["description"] and card["url"] and card["version"]
    assert isinstance(card["capabilities"], dict) and card["skills"]
