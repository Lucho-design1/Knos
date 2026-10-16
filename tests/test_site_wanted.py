"""The demand check's wake page is part of the Pages site: scripts/build_site.sh carries web/wanted.html, which pings
the free Render instance's /healthz until it answers and then opens the app."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import _posix

ROOT = Path(__file__).resolve().parents[1]


def test_the_built_site_serves_the_wake_page(tmp_path: Path):
    site = tmp_path / "site"
    env = _posix.environ({**os.environ, "PYTHON": _posix.path(sys.executable), "PYTHONPATH": str(ROOT / "src")})
    built = subprocess.run([_posix.bash(), _posix.path(ROOT / "scripts" / "build_site.sh"), _posix.path(site), "c" * 40],
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert built.returncode == 0, built.stdout + built.stderr
    page = (site / "wanted.html").read_text(encoding="utf-8")
    assert page == (ROOT / "web" / "wanted.html").read_text(encoding="utf-8")
    assert "https://knos.onrender.com" in page and "/healthz" in page and "location.replace" in page
    assert not (ROOT / "docs" / "wanted.html").exists()          # Pages builds from web/, not docs/
