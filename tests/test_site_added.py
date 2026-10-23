"""Pages added to the site by name (web/views.js ADDED).

tests/web/added.mjs drives the mount in headless Chromium on a build of web/: the link in the menu, the grey bars at
the press, the module's drawing, the enforcement matrix on data of the documented shape, and the width of each.
No node, no `playwright` package or no browser: that part is skipped, with the reason.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import _posix
import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = "/opt/pw-browsers"          # where this project's machines keep Chromium; anywhere else playwright's default holds


def test_the_build_offers_only_the_pages_it_holds(tmp_path: Path):
    site = tmp_path / "site"
    env = _posix.environ({**os.environ, "PYTHON": _posix.path(sys.executable), "PYTHONPATH": str(ROOT / "src")})
    built = subprocess.run([_posix.bash(), _posix.path(ROOT / "scripts" / "build_site.sh"), _posix.path(site), "c" * 40],
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert built.returncode == 0, built.stdout + built.stderr
    views = (site / "views.js").read_text(encoding="utf-8")
    assert "export const ADDED = {" in views and "export const VIEWS" in views
    for line in (ROOT / "web" / "views.js").read_text(encoding="utf-8").splitlines():
        if not line.startswith("  ") or '{ file: "./' not in line:
            continue
        name, file = line.split(":")[0].strip(), line.split('file: "./')[1].split('"')[0]
        data = line.split('json: "')[1].split('"')[0] if 'json: "' in line else None
        held = (site / file).is_file() and (data is None or (site / data).is_file())
        assert (line in views) == held, name
        if data and (site / data).is_file():
            json.loads((site / data).read_text(encoding="utf-8"))


def test_the_added_pages_in_a_browser(tmp_path: Path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    site = tmp_path / "site"
    env = _posix.environ({**os.environ, "PYTHON": _posix.path(sys.executable), "PYTHONPATH": str(ROOT / "src")})
    if "PLAYWRIGHT_BROWSERS_PATH" not in env and Path(BROWSERS).is_dir():
        env["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS
    built = subprocess.run([_posix.bash(), _posix.path(ROOT / "scripts" / "build_site.sh"), _posix.path(site), "c" * 40],
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert built.returncode == 0, built.stdout + built.stderr
    run = subprocess.run([node, str(ROOT / "tests" / "web" / "added.mjs"), str(site)], env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    said = run.stdout.strip().splitlines()
    if run.returncode == 0 and said and said[-1].startswith("SKIP"):
        pytest.skip(said[-1][5:])
    assert run.returncode == 0, "\n".join(line for line in (run.stdout + run.stderr).splitlines() if not line.startswith("ok"))
    assert "added: every check held" in run.stdout
