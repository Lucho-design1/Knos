"""When Qloo cannot answer a new idea, the card answers from the nearest idea Qloo has already answered, with no Qloo
call (knos_wanted.nearest, recorded.honest). SYNTHETIC reports only."""
from knos_wanted import nearest, recorded


def rep(idea, made, tags=()):
    return {"idea": idea, "made": made, "label": "LIVE Qloo data (synthetic test)", "stage": "full", "hash": idea.replace(" ", "")[:16].ljust(64, "0"),
            "tags": [{"id": f"t{i}", "name": t} for i, t in enumerate(tags)], "decision": {"verdict": "REFUSE", "reasons": []},
            "calls": [{"n": 1, "call": "GET /search", "params": {"query": idea}}]}


ANSWERED = [rep("a smart water bottle that glows", "2026-10-22T10:00:00Z", ["Hydration"]),
            rep("a bamboo toothbrush brand", "2026-10-22T11:00:00Z", ["Oral Care"]),
            rep("a water bottle that harvests water from air", "2026-10-22T12:00:00Z")]


def test_stop_words_drop_and_words_stem():
    assert nearest.stems("The Runners of a Festival") == {"runn", "festival"}


def test_the_most_shared_words_win_and_a_tie_goes_to_the_newest():
    got = nearest.find("a water bottle for hikers", ANSWERED)
    assert got["count"] == 2 and got["report"]["idea"] == "a water bottle that harvests water from air"   # tie at 2: newest
    got = nearest.find("a smart bottle that glows", ANSWERED)
    assert got["report"]["idea"] == "a smart water bottle that glows" and got["count"] == 3


def test_the_qloo_tags_names_count_too():
    assert nearest.shared("a hydration tracker", ANSWERED[0]) == 1
    assert nearest.find("an oral care subscription", ANSWERED)["report"]["idea"] == "a bamboo toothbrush brand"


def test_under_2_shared_the_3_nearest_are_offered():
    got = nearest.find("a vinyl record shop", ANSWERED)
    assert "report" not in got and len(got["options"]) == 3


def test_a_429_answers_from_the_nearest_recording(monkeypatch):
    monkeypatch.setattr(recorded, "_last", {})
    monkeypatch.setattr(recorded, "_answered", {recorded.key(r["idea"]): r for r in ANSWERED})
    failed = {"idea": "a smart bottle that glows", "calls": [{"n": 1, "error": "HTTP 429: not sent: the month is used up"}], "decision": {"verdict": "CANNOT_DECIDE"}}
    out = recorded.honest("a smart bottle that glows", failed)
    assert out["nearest"] == {"asked": "a smart bottle that glows", "idea": "a smart water bottle that glows", "on": "2026-10-22", "shared": 3}
    assert out["idea"] == "a smart water bottle that glows" and out["stale"]["code"] == 429
    out = recorded.honest("a vinyl record shop", {**failed, "idea": "a vinyl record shop"})
    assert len(out["nearest_options"]) == 3 and "nearest" not in out
    exact = recorded.honest("a bamboo toothbrush brand", {**failed, "idea": "a bamboo toothbrush brand"})
    assert exact["idea"] == "a bamboo toothbrush brand" and exact["stale"] and "nearest" not in exact
