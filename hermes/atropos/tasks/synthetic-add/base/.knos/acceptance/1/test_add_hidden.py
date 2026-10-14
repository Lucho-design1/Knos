from calc import add


def test_add_small():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-4, 1) == -3
