#!/bin/sh
# One command: PyLabRobot 0.2.2 in its own venv, for Knos's robotics re-runs in live mode.
#
#   sh scripts/install_pylabrobot.sh [VENV_DIR]          (default: ~/.knos/pylabrobot-venv)
#
# It never touches the Knos install. At the end it prints the line to add to your shell:
#   export KNOS_PYLABROBOT_PYTHON=<VENV_DIR>/bin/python
# Then `python -m knos.labs try pylabrobot --live` and `python scripts/labs_pylabrobot_check.py` run the simulator.
# Without it, Knos uses the RECORDED runs (src/knos/labs/fixtures/pylabrobot.json), labelled FIXTURE.
set -eu
VENV="${1:-$HOME/.knos/pylabrobot-venv}"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else "PyLabRobot needs Python 3.9 or newer")'
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "pylabrobot==0.2.2"
"$VENV/bin/python" -c 'import pylabrobot; print("PyLabRobot", pylabrobot.__version__, "installed")'
echo "export KNOS_PYLABROBOT_PYTHON=$VENV/bin/python"
