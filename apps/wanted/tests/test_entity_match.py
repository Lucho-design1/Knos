"""An entity Qloo returns is a match for the idea only when it shares a Qloo tag with the idea's tags or names what the
idea is; a kept card whose matches change is decided again. SYNTHETIC values only."""
from knos_wanted import check

TAGS = [{"name": "Family Meal Planners", "id": "urn:tag:x:family_meal_planners"}]


def test_the_category_word_is_the_ideas_last_word_found_in_its_tags():
    assert check.category_word("an AI recipe planner for families", TAGS) == "family"
    assert check.category_word("a quantum physics book for kids", [{"name": "Quantum Physics"}]) == "physic"
    assert check.category_word("a tea", []) is None


def test_a_shared_tag_or_the_category_word_makes_a_match_and_a_name_alone_does_not():
    cafe = {"name": "Secret Recipe Cafe", "about": "a cafe chain known for cakes", "tag_ids": []}
    assert not check.entity_tied(cafe, "an AI recipe planner for families", TAGS)
    assert check.entity_tied({**cafe, "tag_ids": ["urn:tag:x:family_meal_planners"]}, "an AI recipe planner for families", TAGS)
    assert check.entity_tied({"name": "Mealime", "about": "a meal planner for busy families"}, "an AI recipe planner for families", TAGS)


def test_a_kept_card_loses_an_untied_match_and_is_decided_again():
    rep = {"idea": "an AI recipe planner for families", "tags": TAGS, "words": ["recipe", "planner", "familie"],
           "matches": [{"name": "Secret Recipe Cafe", "id": "e1", "about": "cakes", "matched_words": ["recipe"], "name_words": ["recipe"]}],
           "leader": {"name": "Secret Recipe Cafe", "id": "e1"}, "unrelated": [], "cities": [{"name": "Richmond", "because": ["e1"]}],
           "decision": {"verdict": "OPEN"}}
    out = check.retie(rep)
    assert out["matches"] == [] and out["leader"] is None and out["cities"][0]["because"] == []
    assert out["unrelated"][0]["name"] == "Secret Recipe Cafe" and out["decision"]["verdict"] == "REFUSE"
