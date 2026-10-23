"""TASK-WORLD T4 test_hero_needs, the page half: the hero's examples cover housing, food, energy and health, across at
least five technologies, on every copy of the hero (the live half is scripts/test_world_live.py)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEEDS = {"housing", "food", "energy", "health"}


def chips(html: str) -> list[dict]:
    """The example chips (each names its technology), not the chips a script builds."""
    return [dict(re.findall(r'data-(\w+)="([^"]*)"', m)) for m in re.findall(r'<button[^>]*class="k-chip" data-tech[^>]*>', html)]


@pytest.mark.parametrize("page", ["web/brand/hero.html", "web/index.html"])
def test_hero_needs(page):
    c = chips((ROOT / page).read_text(encoding="utf-8"))
    assert NEEDS <= {x.get("need") for x in c}, page
    assert len({x["tech"] for x in c if x.get("tech")}) >= 5, page
    assert all(x.get("q") for x in c)
