"""A segment of a sensitive type (Qloo's entity_id names it) or named for a belief is never shown, and a card recorded
before that rule held is shown without it; taste tags are left alone. SYNTHETIC values only."""
from knos_wanted import check


def test_a_beliefs_segment_is_refused_by_its_entity_id_or_its_name():
    assert not check.safe_segment({"entity_id": "urn:audience:lifestyle_preferences_beliefs:x", "name": "Organic Ingredients"})
    assert not check.safe_segment({"name": "Judaism", "disambiguation": "Lifestyle Preferences Beliefs"})
    assert check.safe_segment({"entity_id": "urn:audience:hobbies_and_interests:video_gamer", "name": "Video Gamer"})


def test_a_kept_card_is_shown_without_its_sensitive_segments_and_its_tags_stay():
    rep = {"versus": {"method": "shared audience segments (Qloo has too few tags to compare)",
                      "whitespace": ["Judaism (Lifestyle Preferences Beliefs)", "Video Gamer (Hobbies And Interests)"]},
           "audiences": [{"name": "Judaism (Lifestyle Preferences Beliefs)"}, {"name": "Cinephile (Leisure)"}], "decision": {"verdict": "OPEN"}}
    out = check.scrub(rep)
    assert out["versus"]["whitespace"] == ["Video Gamer (Hobbies And Interests)"] and [a["name"] for a in out["audiences"]] == ["Cinephile (Leisure)"]
    assert out["decision"] == rep["decision"]
    tags = {"versus": {"method": "shared taste tags (compare)", "whitespace": ["Health", "Drinks"]}}
    assert check.scrub(tags)["versus"]["whitespace"] == ["Health", "Drinks"]
