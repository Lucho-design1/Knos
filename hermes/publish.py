"""Publish the Knos Hermes skill (hermes/knos/) the two ways Hermes Agent discovers skills from outside its hub.

    python hermes/publish.py well-known     writes web/.well-known/skills/index.json and a copy of each skill's files
                                            under web/.well-known/skills/<name>/ (the site serves web/ as it is)
    python hermes/publish.py tap OUT        writes a GitHub tap layout into OUT: OUT/skills/<name>/... and a README;
                                            push OUT as its own repository and users run
                                            `hermes skills tap add <owner>/<repo>`
    python hermes/publish.py check          exit 1 when the committed well-known copy differs from hermes/knos/

The formats are Hermes Agent's (NousResearch/hermes-agent@8f817911):
    well-known   tools/skills_hub_sources.py WellKnownSkillSource: GET <base>/.well-known/skills/index.json ->
                 {"skills": [{"name", "description", "files": [...]}]}, then <base>/.well-known/skills/<name>/<file>
    tap          website/docs/user-guide/features/skills.md "Publishing a custom skill tap": skills/<name>/SKILL.md
                 (+ references/, scripts/, templates/, assets/), the directory name is the install slug
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = [ROOT / "hermes" / "knos"]
WELL_KNOWN = ROOT / "web" / ".well-known" / "skills"


def frontmatter(text: str) -> dict:
    """The two scalar fields the index needs (name, description), read without a YAML dependency."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for key in ("name", "description"):
        hit = re.search(rf"^{key}:\s*(.+)$", m.group(1) if m else "", re.M)
        out[key] = hit.group(1).strip().strip("'\"") if hit else ""
    return out


def files_of(skill: Path) -> list[str]:
    return sorted(p.relative_to(skill).as_posix() for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def index() -> dict:
    rows = []
    for skill in SKILLS:
        fm = frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
        rows.append({"name": fm["name"] or skill.name, "description": fm["description"], "files": files_of(skill)})
    return {"skills": rows}


def well_known(out: Path = WELL_KNOWN) -> list[Path]:
    written = []
    out.mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        dest = out / skill.name
        if dest.exists():
            shutil.rmtree(dest)
        for rel in files_of(skill):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(skill / rel, dest / rel)
            written.append(dest / rel)
    (out / "index.json").write_text(json.dumps(index(), indent=2) + "\n", encoding="utf-8")
    return [*written, out / "index.json"]


def tap(out: Path) -> list[Path]:
    written = []
    for skill in SKILLS:
        for rel in files_of(skill):
            dest = out / "skills" / skill.name / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(skill / rel, dest)
            written.append(dest)
    readme = out / "README.md"
    readme.write_text("# Knos skills for Hermes Agent\n\nA Hermes skills tap. Add it with `hermes skills tap add <owner>/<this repo>`, "
                      "then `hermes skills install <owner>/<this repo>/knos`.\n\nGenerated from hermes/knos/ of "
                      "https://github.com/drexthealpha/Knos by hermes/publish.py; edit it there.\n", encoding="utf-8")
    return [*written, readme]


def differences(out: Path = WELL_KNOWN) -> list[str]:
    bad = []
    try:
        if json.loads((out / "index.json").read_text(encoding="utf-8")) != index():
            bad.append("index.json")
    except (OSError, ValueError):
        bad.append("index.json")
    for skill in SKILLS:
        for rel in files_of(skill):
            copy = out / skill.name / rel
            if not copy.is_file() or copy.read_bytes() != (skill / rel).read_bytes():
                bad.append(f"{skill.name}/{rel}")
        extra = set(files_of(out / skill.name)) - set(files_of(skill)) if (out / skill.name).is_dir() else set()
        bad += [f"{skill.name}/{x} (not in the source)" for x in sorted(extra)]
    return bad


def main(argv: list[str]) -> int:
    if argv[:1] == ["well-known"]:
        for p in well_known():
            print(p.relative_to(ROOT))
        return 0
    if argv[:1] == ["tap"] and len(argv) == 2:
        for p in tap(Path(argv[1])):
            print(p)
        return 0
    if argv[:1] == ["check"]:
        bad = differences()
        print("in step" if not bad else "out of step: " + ", ".join(bad) + " (run: python hermes/publish.py well-known)")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
