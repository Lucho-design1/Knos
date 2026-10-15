import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from calc import add  # noqa: E402


def test_add():
    assert add(2, 3) == 5
