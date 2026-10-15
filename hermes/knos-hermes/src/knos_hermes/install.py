"""Put the plugin where Hermes looks for it.

Hermes discovers memory providers by scanning directories — bundled ones in
`plugins/memory/<name>/`, and yours in `$HERMES_HOME/plugins/<name>/`. It does
not read pip entry points; `plugins/memory/__init__.py` in hermes-agent has no
`importlib.metadata` call anywhere. CONTRIBUTING.md says "or via a pip entry
point", and that is not what the loader does.

So `pip install knos-hermes` cannot register anything by itself. This copies
the plugin directory into place, which is the one step the loader can see.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "knos"


def hermes_home() -> Path:
    """Where Hermes keeps its state, resolved the way Hermes resolves it.

    `HERMES_HOME` first, then the platform default — matching
    `hermes_constants.get_hermes_home()`. If the two ever disagree the plugin
    lands somewhere Hermes will not look, so this mirrors it rather than
    guessing.
    """
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "hermes"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "hermes"
    return Path.home() / ".hermes"


def source_dir() -> Path:
    return Path(__file__).resolve().parent / "plugin"


def install(target_home: Path | None = None) -> Path:
    """Copy the plugin into `$HERMES_HOME/plugins/knos/`. Returns where it went."""
    home = target_home or hermes_home()
    target = home / "plugins" / PLUGIN_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    # Ignore build cruft: a __pycache__ compiled against this interpreter is
    # wrong for whichever Python Hermes runs, and Hermes scans the directory.
    shutil.copytree(
        source_dir(), target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    return target


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print("knos-hermes install     put the provider where Hermes looks")
        print("knos-hermes where       print that path and stop")
        return 0
    if argv and argv[0] == "where":
        print(hermes_home() / "plugins" / PLUGIN_NAME)
        return 0

    try:
        target = install()
    except OSError as why:
        print(f"Could not install: {why}", file=sys.stderr)
        return 1

    print(f"Installed to {target}")
    print("")
    print("Turn it on, in Hermes:")
    print("  hermes memory setup        and pick knos")
    print("")
    print("Or set it by hand in $HERMES_HOME/config.yaml:")
    print("  memory:")
    print("    provider: knos")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
