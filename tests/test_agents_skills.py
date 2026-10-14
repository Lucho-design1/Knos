"""The agent skills: Claude Code (plugin/skills/, loaded with the Knos plugin), OpenClaw (integrations/skills/openclaw/), Hermes (hermes/knos/), the site's
/.well-known/skills/ copy and the tap layout. Each says the same three things: run knos verify before a pull request,
never open one where the AI policy bans it, disclose AI use."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / "plugin" / "skills" / "knos-verify" / "SKILL.md"      # the Claude Code plugin (plugin/) loads its skills/
OPENCLAW = ROOT / "integrations" / "skills" / "openclaw" / "knos-verify" / "SKILL.md"
HERMES = ROOT / "hermes" / "knos"
sys.path.insert(0, str(ROOT / "hermes"))
import publish  # noqa: E402


def _front(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} has no front matter"
    return yaml.safe_load(m.group(1)), m.group(2)


@pytest.mark.parametrize("path", [CLAUDE, OPENCLAW, HERMES / "SKILL.md"])
def test_every_skill_says_verify_obey_the_policy_and_disclose(path):
    fm, body = _front(path)
    assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*", fm["name"]) and len(fm["name"]) <= 64          # Hermes skill_linter, Agent Skills
    assert 20 <= len(fm["description"]) <= 1024
    low = " ".join(body.lower().split())
    assert "knos verify" in low and "banned" in low and "ai-use line" in low.replace("ai use line", "ai-use line")
    assert "do not open the pull request" in low or "never open a pull request" in low
    assert "never edit" in low or "never weaken" in low


def test_the_claude_code_skill_allows_only_the_commands_it_needs():
    fm, _ = _front(CLAUDE)
    assert fm["name"] == CLAUDE.parent.name and fm["allowed-tools"].startswith("Bash(knos verify:*)")


def test_the_openclaw_skill_carries_its_metadata_as_one_line_of_json():
    text = OPENCLAW.read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if x.startswith("metadata:"))
    meta = json.loads(line.split(":", 1)[1])
    assert meta["openclaw"]["requires"]["bins"] == ["knos", "git"] and set(meta["openclaw"]["os"]) <= {"darwin", "linux", "win32"}


def test_the_hermes_skill_has_the_agentskills_frontmatter_hermes_reads():
    fm, body = _front(HERMES / "SKILL.md")
    assert fm["name"] == "knos" == HERMES.name and fm["version"] == "0.3.29" and fm["license"] == "MIT"
    h = fm["metadata"]["hermes"]
    assert h["tags"] and h["category"] and h["requires_tools"] == ["terminal"]
    (env,) = fm["required_environment_variables"]
    assert set(env) == {"name", "prompt", "help", "required_for"} and env["name"] == "GH_TOKEN"
    assert set(fm["platforms"]) <= {"linux", "macos", "windows"}
    assert "## When to Use" in body and len(body) < 24_000                                     # tools/skill_linter.py
    assert (HERMES / "scripts" / "knos-verify.sh").read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert {p.name for p in (HERMES / "references").iterdir()} == {"ai-policy.md", "receipt.md", "tools.md"}


def test_the_well_known_copy_is_in_step_with_the_skill_and_the_index_has_hermes_shape():
    assert publish.differences() == [], "run: python hermes/publish.py well-known"
    idx = json.loads((ROOT / "web" / ".well-known" / "skills" / "index.json").read_text(encoding="utf-8"))
    (row,) = idx["skills"]
    assert row["name"] == "knos" and "SKILL.md" in row["files"] and all(not f.startswith(("/", "..")) for f in row["files"])


def test_the_tap_layout_is_skills_name_skill_md(tmp_path):
    written = publish.tap(tmp_path / "tap")
    assert (tmp_path / "tap" / "skills" / "knos" / "SKILL.md").is_file() and (tmp_path / "tap" / "README.md").is_file()
    assert len(written) == len(publish.files_of(HERMES)) + 1
    assert subprocess.run([sys.executable, str(ROOT / "hermes" / "publish.py"), "check"], capture_output=True).returncode == 0
