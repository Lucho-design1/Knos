from slugs import slug


def test_lower():
    assert slug("ABC") == "abc"
