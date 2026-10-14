from text import slug


def test_slug_spaces():
    assert slug("Hello  World") == "hello-world"


def test_slug_trim():
    assert slug("  A b ") == "a-b"
