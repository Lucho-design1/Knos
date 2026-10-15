import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from calc2 import mul  # noqa: E402


def test_mul():
    assert mul(2, 3) == 6
