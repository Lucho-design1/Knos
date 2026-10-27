"""A result's receipts (knos_wanted.receipts): one row per source of a number on the card, each hash recomputing from
what the row shows. SYNTHETIC report only; the Knos record is not touched."""
import hashlib
import json

from knos import ready
from knos_wanted import metros, receipts


def report():
    cells = [{"lat": 36.17 + i * 0.01, "lon": -115.14, "affinity": 0.99 - i * 0.02} for i in range(4)] + [{"lat": 40.7, "lon": -74.0, "affinity": 0.5}]
    t = metros.terms(cells)
    return {"hash": "ab" * 32, "idea": "a synthetic desert music festival", "made": "2026-10-22T22:09:40Z", "matches": [{"id": "e1", "name": "X"}],
            "terms": t, "where": cells, "persona": [{"name": "Festival Goers"}],
            "calls": [{"n": 1, "call": "GET /search", "what": "closest products", "params": {"query": "desert festival", "take": 5},
                       "at": "2026-10-22T22:09:00Z", "body_digest": "5 results: X"},
                      {"n": 2, "call": "GET /v2/insights", "params": {"filter.type": "urn:heatmap"}, "at": "2026-10-22T22:09:10Z", "body_digest": "4 cells"}],
            "model_alone": {"city": "Indio, California", "who": "fans", "why": "deserts", "model": "m", "at": "2026-10-27T08:00:00Z"}}


def test_each_hash_recomputes_from_its_row(monkeypatch):
    monkeypatch.setattr(receipts, "record_line", lambda rep: {"recorded": True, "seq": 7, "kind": "claim", "claim": "c" * 64})
    rows = {r["id"]: r for r in receipts.rows(report())}
    for n in (1, 2):
        r = rows[f"call-{n}"]
        body = json.dumps(r["call"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert r["source"] == "qloo" and r["hash"] == hashlib.sha256(body.encode()).hexdigest() and r["trace"].endswith(f"#call-{n}")
    assert rows["brief"]["hash"] == ready.criteria_hash(rows["brief"]["brief"])
    assert rows["rule-target"]["value"] == report()["terms"]["target"] and rows["model"]["value"] == "Indio, California"
    assert rows["record"]["seq"] == 7 and rows["chain"]["transactions"] == []


def test_the_page_gives_each_row_its_anchor(monkeypatch):
    monkeypatch.setattr(receipts, "record_line", lambda rep: {"recorded": False, "why": "none here"})
    html = receipts.page(report(), "ab" * 8)
    for rid, src in (("call-1", "qloo"), ("rule-target", "rule"), ("brief", "rule"), ("model", "model"), ("record", "record"), ("chain", "chain")):
        assert f'<tr id="{rid}" data-source="{src}">' in html
