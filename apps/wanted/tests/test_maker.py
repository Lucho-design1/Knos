"""MAKER flow: find_tags + describe -> the maker CONFIRMS -> demographics + entity tags -> where -> trends ->
compare -> rank -> demand report with its request-to-result trail."""
from datetime import date

import pytest

from knos_wanted import demand
from knos_wanted.mock_mcp import MOCK_LABEL

IDEA = "A late-night oat-milk coffee bar for students in London"
ORDER = ["qloo_audience_demographics", "qloo_entity_tags", "qloo_where_popular", "qloo_trends", "qloo_compare_audiences", "qloo_rank"]


def run(q, pick, **kw):
    s = demand.start(q, IDEA, ["Starbucks", "Pret"], "London", **kw)
    return s, demand.confirm(q, s, pick(s), today=date(2026, 10, 14))


def test_nothing_is_asked_before_the_maker_confirms(q):
    s = demand.start(q, IDEA, ["Starbucks"], "London")
    assert [t["tool"] for t in s["trail"]] == ["qloo_find_tags"] * 3 + ["qloo_describe"] * 2
    kinds = [x["kind"] for x in s["questions"]]
    assert kinds == ["tag", "tag", "tag", "proxy", "rival"] and all(x["candidates"] for x in s["questions"])
    assert s["questions"][3]["status"] == "needs_input"


def test_full_report_uses_the_chain_in_order(q, pick):
    s, r = run(q, pick)
    tools = [t["tool"] for t in r["trail"] if t["tool"]]
    assert tools[6:] == ORDER
    confirmed = [t for t in r["trail"] if t["status"] == "confirmed"]
    assert len(confirmed) == 6 and all(t["chosen"] for t in confirmed)
    for sec in ("who", "where", "rising", "rivals", "fit"):
        assert r[sec]["status"] == "ok", sec
    assert r["label"] == MOCK_LABEL and r["aggregate"] == "aggregate taste, not a prediction about one person"
    assert r["framing"] == "Directional demand evidence, not a sales forecast."
    assert r["lean"]["word"] in ("leans wanted", "mixed", "weak") and r["lean"]["sections_used"] == 3
    assert {x["role"] for x in r["fit"]["rows"]} == {"proxy", "rival"} and len(r["rising"]["series"]) == 3
    rank_req = next(t for t in r["trail"] if t["tool"] == "qloo_rank")["request"]
    assert rank_req["signal_location"] == "London" and len(rank_req["options"]) == 3


def test_only_offered_candidates_are_accepted(q):
    s = demand.start(q, IDEA, [], "London")
    key = next(x["key"] for x in s["questions"] if x["kind"] == "proxy")
    with pytest.raises(demand.FlowError, match="candidates"):
        demand.confirm(q, s, {key: "mock-place-made-up-a"})
    with pytest.raises(demand.FlowError, match="at least one"):
        demand.confirm(q, s, {})


def test_search_another_name_adds_candidates(q):
    s = demand.start(q, IDEA, [], "London")
    key = next(x["key"] for x in s["questions"] if x["kind"] == "proxy")
    before = len(next(x for x in s["questions"] if x["key"] == key)["candidates"])
    got = demand.search(q, s, key, "Blank Street")
    assert len(got["candidates"]) == before + 3 and s["trail"][-1]["why"].startswith("the maker searched")


def test_same_choices_same_hash_and_sections_degrade(q, pick):
    _, a = run(q, pick)
    _, b = run(q, pick)
    assert a["hash"] == b["hash"] and len(a["hash"]) == 64
    s = demand.start(q, "A late-night oat-milk coffee bar for students", [], None)
    r = demand.confirm(q, s, pick(s), today=date(2026, 10, 14))
    assert r["where"]["status"] == "no input" and r["fit"]["status"] == "no input" and r["rivals"]["status"] == "no input"
    assert r["who"]["status"] == "ok"           # the rest of the report still stands


def test_failed_call_marks_its_section_only(q, pick, monkeypatch):
    from knos_wanted.qloo_mcp import InProcess, Qloo
    c = Qloo(InProcess(fail="qloo_where_popular:QLOO_FORBIDDEN:fatal:9"), mode="mock", sleep=lambda s: None)
    s = demand.start(c, IDEA, ["Pret"], "London")
    r = demand.confirm(c, s, pick(s), today=date(2026, 10, 14))
    assert r["where"]["status"] == "error" and r["who"]["status"] == "ok" and r["fit"]["status"] == "ok"


def test_lean_rule():
    r = {"fit": {"rows": [{"rank": 1, "role": "proxy", "affinity": 0.9}, {"rank": 2, "role": "rival", "affinity": 0.5}]},
         "rising": {"series": [{"role": "proxy", "name": "P", "direction": "rising", "change_points": 3.0}]},
         "who": {"segments": [{"label": "25 to 29", "score": 0.3}]}}
    assert demand.lean(r)["word"] == "leans wanted"
    r["fit"]["rows"][0]["rank"], r["fit"]["rows"][1]["rank"] = 2, 1
    r["rising"]["series"][0]["direction"] = "falling"
    assert demand.lean(r)["word"] == "weak"
    assert demand.lean({"who": {"segments": [{"label": "x", "score": 0.5}]}})["word"] == "insufficient evidence"


def test_demographic_phrase():
    assert demand.demographic_phrase({"age": ["24_and_younger"], "gender": "female"}) == "young women"
    assert demand.demographic_phrase({"age": ["25_to_29", "30_to_34"], "gender": None}) == "millennials"
    assert demand.demographic_phrase({"age": [], "gender": None}) is None
