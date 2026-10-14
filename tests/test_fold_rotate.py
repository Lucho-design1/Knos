"""knos-oidc-rotate in Knos (docs/reference/MONOREPO.md, CUTOVER-0331.md): its files at the commit the second deployment
pins last are workflows/knos-oidc-rotate/, byte for byte the git tree of that commit, inactive there; the programs still
pin the old repository until the founder's Squads-signed upgrade; and the cutover page names every step."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / "workflows" / "knos-oidc-rotate"
TREE_212F9EB5 = "a7302cf65b15dc2b9280217a3b47239ac7527d48"     # `git rev-parse 212f9eb5^{tree}` in drexthealpha/knos-oidc-rotate


def _pub():
    spec = importlib.util.spec_from_file_location("pinned_workflows_rotate", ROOT / "scripts" / "pinned_workflows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_copy_is_the_tree_of_the_pinned_commit_and_asks_for_an_id_token():
    files = {p.relative_to(COPY).as_posix(): p.read_bytes() for p in COPY.rglob("*") if p.is_file()}
    assert sorted(files) == [".github/workflows/claim.yml", ".github/workflows/rotate.yml", "LICENSE", "README.md"]
    assert _pub().tree_id(files) == TREE_212F9EB5
    rotate = files[".github/workflows/rotate.yml"].decode("utf-8")
    assert "id-token: write" in rotate and "workflow_call:" in rotate and "schedule:" in rotate
    # inactive here: Knos's own workflows are .github/workflows/ at the root, and none of them is this file
    assert not (ROOT / ".github" / "workflows" / "rotate.yml").exists()


def test_the_programs_still_pin_the_old_repository_and_its_commits():
    pins = (ROOT / "programs-v2" / "knos_oidc" / "src" / "pins.rs").read_text(encoding="utf-8")
    ids = json.loads((ROOT / "programs-v2" / "program_ids.json").read_text(encoding="utf-8"))
    assert 'pub const ROTATE_REF: &[u8] = b"drexthealpha/knos-oidc-rotate/.github/workflows/rotate.yml@";' in pins
    assert ids["rotate_sha"].startswith("6ddf031b") and ids["rotate_sha2"].startswith("212f9eb5") and ids["rotate_sha2"] in pins
    lib = (ROOT / "programs-v2" / "knos_pay" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert 'pub const CLAIM_REF: &[u8] = b"drexthealpha/knos-oidc-rotate/.github/workflows/claim.yml@";' in lib


def test_the_cutover_page_names_the_anchor_the_constants_the_squads_step_and_what_still_points_at_it():
    page = (ROOT / "docs" / "reference" / "CUTOVER-0331.md").read_text(encoding="utf-8")
    ids = json.loads((ROOT / "programs-v2" / "program_ids.json").read_text(encoding="utf-8"))
    for word in ("knos-oidc-rotate", "ROTATE_REF", "CLAIM_REF", "Squads", ids["upgrade_multisig"], ids["upgrade_authority"], "knos-workflows",
                 TREE_212F9EB5, "gh repo delete drexthealpha/knos-oidc-rotate --yes", "gh repo delete drexthealpha/knos-workflows --yes"):
        assert word in page, word
    assert re.search(r"\| knos-workflows \| knos_pay 2\.1 orders \| \d+ open \|", page)
    assert "| [CUTOVER-0331.md](CUTOVER-0331.md) |" in (ROOT / "docs" / "reference" / "README.md").read_text(encoding="utf-8")
