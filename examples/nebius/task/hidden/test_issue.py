"""Sealed acceptance tests of the parse_duration task. The coding agent never sees this file."""
import pytest

import duration


@pytest.mark.parametrize("text,want", [("1h30m", 5400), ("45s", 45), ("2d", 172800), ("1h 5m 10s", 3910),
                                       ("  2H ", 7200), ("0s", 0), ("1d2h3m4s", 93784), ("90m", 5400)])
def test_parses(text, want):
    assert duration.parse_duration(text) == want


@pytest.mark.parametrize("text", ["", "   ", "10", "5x", "1h1h", "5m1h", "h", "1.5h", "-3s"])
def test_refuses(text):
    with pytest.raises(ValueError):
        duration.parse_duration(text)
