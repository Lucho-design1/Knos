from datetime import date

from knos_wanted import report
from knos_wanted.qloo import MOCK_LABEL, Qloo

IDEA = "A late-night oat-milk coffee bar for students in London, rivals: Pret, Costa"
DAY = date(2026, 10, 14)


def test_mock_report_has_every_section_and_label():
    r = report.build(IDEA, q=Qloo(), today=DAY)
    assert r["label"] == MOCK_LABEL and r["mode"] == "mock"
    assert r["framing"] == "Directional demand evidence, not a sales forecast."
    for s in ("who", "where", "strength", "rising", "why", "compare"):
        assert r[s]["status"] == "ok", s
    assert {c["endpoint"] for c in r["calls"]} == {"search", "tags", "insights", "demographics", "heatmap", "trending", "compare"}
    assert {x["role"] for x in r["strength"]["rows"]} == {"proxy", "rival"}
    assert r["rising"]["direction"] in ("rising", "flat", "falling")
    assert r["lean"]["word"] in ("leans wanted", "mixed", "weak", "insufficient evidence")
    assert len(r["hash"]) == 64


def test_same_idea_same_hash():
    a = report.build(IDEA, q=Qloo(), today=DAY)
    b = report.build(IDEA, q=Qloo(), today=DAY)
    assert a["hash"] == b["hash"]
    assert report.build(IDEA + " near campus", q=Qloo(), today=DAY)["hash"] != a["hash"]


def test_live_degrades_per_endpoint(fake, tmp_path):
    f = fake({"heatmap": 403, "compare": 404, "trending": 401})
    q = Qloo(api_key="k", opener=f, cache_dir=tmp_path / "c", unserved=set())
    r = report.build(IDEA, q=q, today=DAY)
    assert r["mode"] == "live" and r["label"] == report.LIVE_LABEL
    assert r["where"]["status"] == "not served"
    assert r["compare"]["status"] == "not served"
    assert r["rising"]["status"] == "not served"
    assert r["who"]["status"] == "ok" and r["strength"]["status"] == "ok" and r["why"]["status"] == "ok"
    assert any(c["status"] == "not served" and c["http"] == 403 for c in r["calls"])


def test_network_failure_is_failed_not_crash(fake, tmp_path):
    f = fake({"demographics": 500})
    q = Qloo(api_key="k", opener=f, cache_dir=tmp_path / "c", unserved=set())
    r = report.build(IDEA, q=q, today=DAY)
    assert r["who"]["status"] == "failed"


def test_no_rival_uses_nearest_neighbour():
    r = report.build("Handmade ceramic mugs for parents", q=Qloo(), today=DAY)
    assert r["strength"]["status"] == "ok"
    assert "nearest neighbour" in (r["strength"]["note"] or "")


def test_drivers_reads_several_layouts():
    assert report.drivers({"signal.interests.entities": [{"entity_id": "a", "score": 0.5}]}) == [("a", 0.5)]
    assert report.drivers({"a": 0.3, "warning": "x"}) == [("a", 0.3)]
    assert report.drivers([{"tag_id": "t", "value": 0.2}]) == [("t", 0.2)]
    assert report.drivers(None) == []


def test_lean_rule():
    base = {"strength": {"rows": [{"role": "proxy", "affinity": 0.9}, {"role": "rival", "affinity": 0.5}]},
            "rising": {"status": "ok", "direction": "rising", "change_points": 3.0},
            "who": {"status": "ok", "segments": [{"label": "25 to 29", "score": 0.4}]}}
    assert report.lean(base)["word"] == "leans wanted"
    base["strength"]["rows"][1]["affinity"] = 0.95
    base["rising"]["direction"] = "falling"
    assert report.lean(base)["word"] == "weak"
    assert report.lean({"who": {"status": "not served"}})["word"] == "insufficient evidence"
