"""The launch metros are ranked by lift (mean cell affinity / population share among the candidates), with known
numbers; the taste persona's tags ride in the hashed Ready brief. SYNTHETIC cells and metros."""
from knos import ready
from knos_wanted import metros

BIG = {"cbsa": "10000", "name": "Big City", "pop": 9_000_000}
SMALL = {"cbsa": "20000", "name": "Small City", "pop": 1_000_000}
TINY = {"cbsa": "30000", "name": "Tiny Town", "pop": 50_000}


def cells(monkeypatch):
    by_lat = {1.0: BIG, 2.0: SMALL, 3.0: TINY}
    monkeypatch.setattr(metros, "metro", lambda lat, lon: by_lat.get(lat))
    big = [{"lat": 1.0, "lon": 0.0, "affinity": a} for a in (0.9, 0.9, 0.9)]       # mean 0.9, share 0.9  -> lift 1.0
    small = [{"lat": 2.0, "lon": 0.0, "affinity": a} for a in (0.5, 0.5, 0.5)]     # mean 0.5, share 0.1  -> lift 5.0
    tiny = [{"lat": 3.0, "lon": 0.0, "affinity": 0.99}]                             # 1 cell: not a candidate
    return big + small + tiny


def test_metro_order_follows_lift_with_known_numbers(monkeypatch):
    rows = metros.stats(cells(monkeypatch))
    assert [r["city"] for r in rows] == ["Small City", "Big City", "Tiny Town"]
    small, big, tiny = rows
    assert (small["share"], small["lift"]) == (0.1, 5.0) and (big["share"], big["lift"]) == (0.9, 1.0) and tiny["lift"] is None
    t = metros.terms(cells(monkeypatch))
    assert t["city"] == "Small City" and t["lift"] == 5.0 and t["target"] == max(10, round(1_000_000 / 100_000 * 0.5))
    assert "population share" in t["method"] and "method 2" in t["method"]


def test_raw_affinity_alone_would_have_picked_the_big_metro(monkeypatch):
    rows = metros.stats(cells(monkeypatch))
    three = [r for r in rows if r["cells"] >= metros.MIN_CELLS]
    assert max(three, key=lambda r: r["affinity"])["city"] == "Big City" and metros.launch(rows)["city"] == "Small City"


def test_the_persona_tags_are_inside_the_criteria_hash(monkeypatch):
    t = metros.terms(cells(monkeypatch))
    a = metros.brief("a synthetic idea", t, ["Tag A", "Tag B"])
    b = metros.brief("a synthetic idea", t, ["Tag A", "Tag C"])
    assert a["launch"]["persona"] == ["Tag A", "Tag B"]
    assert ready.criteria_hash(a) != ready.criteria_hash(b)
    assert ready.criteria_hash(a) == ready.criteria_hash(metros.brief("a synthetic idea", t, ["Tag A", "Tag B"]))
