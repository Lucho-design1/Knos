"""TASK-WORLD T7 test_refuse_list: the published refuse list inside the Ready check. 30 briefs that are otherwise Ready
(a measurable target, a verifier, a deadline), each naming one listed word: 0 of 30 pass. Harmless briefs that share a
word with the list ("bath bomb", "glue gun") still pass."""
from knos import ready, refuse


def brief(title: str, place: str = "") -> dict:
    return {"title": title, "place": place,
            "milestones": [{"key": "m1", "name": "Pilot units", "target": "100 units pass a 72 h soak test at 25 C",
                            "verifier": {"check": "test_soak"}, "deadline_days": 30}]}


def bad_briefs() -> list[tuple[str, dict]]:
    """30 briefs built from the list's own words, spread over the four categories (no product is described)."""
    out = []
    for cat, words in refuse.REFUSE.items():
        for w in words[:8 if cat != "sanctioned_places" else 6]:
            out.append((cat, brief(f"A project named for '{w}'") if cat != "sanctioned_places" else brief("A water filter", place=w.title())))
    return out[:30]


def test_none_of_30_listed_briefs_passes_and_each_names_its_category():
    bad = bad_briefs()
    assert len(bad) == 30 and {c for c, _ in bad} == set(refuse.REFUSE)
    passed = []
    for cat, b in bad:
        r = ready.check(b)
        if r["ready"] or r["label"] != "Refused" or cat not in {x["category"] for x in r["refused"]}:
            passed.append((cat, b["title"], b["place"], r["label"]))
    assert passed == [], passed


def test_the_same_briefs_without_a_listed_word_are_ready_and_harmless_phrases_pass():
    assert ready.check(brief("A water filter"))["ready"]
    for title in ("Bath bombs from local clay", "A cordless glue gun for schools", "Combat sports mouthguard sizing app",
                  "Low-carbon cement blocks for homes", "A kombucha brand", "A home battery that charges at night"):
        r = ready.check(brief(title))
        assert r["ready"] and r["refused"] == [], (title, r["missing"][:3])
    assert ready.check(brief("A water filter", place="Lagos"))["ready"]


def test_the_list_is_published_with_its_date_and_source():
    p = refuse.public()
    assert set(p["categories"]) == {"weapons", "military_first", "dangerous_pathogens", "sanctioned_places"}
    assert p["as_of"] == "2026-10-23" and p["sanctions_source"].startswith("https://ofac.treasury.gov/")
