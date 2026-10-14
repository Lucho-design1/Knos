"""BUYER agent flow: chosen taste signals (never identity) -> confirm -> recommend across target types -> rank the
not-yet-built products by their confirmed proxies, one call per type."""
from datetime import date

import pytest

from knos_wanted import buyer, catalog, demand, privacy


def listed(q, pick, idea, place="London", title="Night Oat Bar"):
    s = demand.start(q, idea, ["Pret"], place)
    rep = demand.confirm(q, s, pick(s), today=date(2026, 10, 14))
    return catalog.publish(rep, title)


def test_identity_data_refused_before_any_call(q):
    sent = []
    q.t.call = lambda name, args: sent.append(name)
    for bad in (["jane.doe@example.com"], ["call me on 07700 900123"], ["@jane"], ["my name is Jane"]):
        with pytest.raises(privacy.PersonalData):
            buyer.start(q, bad)
    assert sent == []


def test_recommend_across_types_and_rank_products(q, pick):
    p1 = listed(q, pick, "A late-night oat-milk coffee bar for students in London")
    p2 = listed(q, pick, "A vegan bakery for parents in London", title="Vegan Morning")
    s = buyer.start(q, "Aesop, Monocle", "minimalist", ["brand", "place", "nonsense"])
    assert s["targets"] == ["brand", "place"]
    assert [t["tool"] for t in s["trail"]] == ["qloo_describe", "qloo_describe", "qloo_find_tags"]
    r = buyer.confirm(q, s, pick(s))
    tools = [t["tool"] for t in r["trail"] if t["tool"]]
    assert tools[3:] == ["qloo_recommend", "qloo_recommend", "qloo_rank"]          # both products are places: one rank
    rec_req = next(t for t in r["trail"] if t["tool"] == "qloo_recommend")["request"]
    assert rec_req["signals"] and rec_req["signal_tags"] and rec_req["explain"] is True
    assert {x["report_hash"] for x in r["products"]} == {p1["report_hash"], p2["report_hash"]}
    assert sorted(x["rank_in_type"] for x in r["products"]) == [1, 2]
    assert r["aggregate"] == "aggregate taste, not a prediction about one person"
    assert all(g["items"] for g in r["recommendations"])


def test_no_products_or_only_tags(q, pick):
    s = buyer.start(q, [], ["cozy"])
    r = buyer.confirm(q, s, pick(s), products=[])
    assert r["products"] == [] and "No product" in r["note"]
    r = buyer.confirm(q, buyer.start(q, [], ["cozy"]), pick(buyer.start(q, [], ["cozy"])),
                      products=[{"report_hash": "a" * 64, "title": "x", "type": "place", "proxy": {"id": "mock-place-x-a", "name": "x"}}])
    assert "liked thing" in r["note"]


def test_choices_must_be_offered(q):
    s = buyer.start(q, "Aesop")
    with pytest.raises(demand.FlowError):
        buyer.confirm(q, s, {s["questions"][0]["key"]: "mock-brand-invented-z"})
    with pytest.raises(demand.FlowError):
        buyer.confirm(q, s, {})
