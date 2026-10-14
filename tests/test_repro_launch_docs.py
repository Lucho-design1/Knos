"""docs/launch/: every link leads to a file, the measured number is the slop audit's own (research/slop_audit/out), and no
page states a percentage of its own."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCH = ROOT / "docs" / "launch"
PAGES = ("README.md", "DEMO.md", "INSTALL.md", "MAINTAINERS.md", "AGENTS.md")


def test_the_four_pages_and_their_links():
    assert sorted(p.name for p in LAUNCH.glob("*.md")) == sorted(PAGES)
    for name in PAGES:
        text = (LAUNCH / name).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            assert target.startswith("https://") or (LAUNCH / target).resolve().exists(), (name, target)


def test_the_number_is_the_slop_audits_and_no_page_has_one_of_its_own():
    import json
    audit = json.loads((ROOT / "research" / "slop_audit" / "out" / "slop_audit.json").read_text(encoding="utf-8"))
    assert '"k": 1119' in json.dumps(audit) and '"n": 3736' in json.dumps(audit)     # the figures the pages quote
    for name in ("DEMO.md", "MAINTAINERS.md", "AGENTS.md"):
        text = (LAUNCH / name).read_text(encoding="utf-8")
        assert "{SLOP_NUMBER}" not in text and "1,119 of 3,736" in text, name
    for name in PAGES:
        text = (LAUNCH / name).read_text(encoding="utf-8")
        assert set(re.findall(r"\d+\s?%", text)) <= {"30%"}, name               # the audit's 1,119 / 3,736, nothing else
        assert "60-second" in text or name != "README.md"
