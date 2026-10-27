"""A result's downloads (knos_wanted.exports): the brief as a one-page PDF, the calls as CSV with no response body and no
key, the Ready brief as JSON with its criteria hash. SYNTHETIC report only."""
import csv
import io
import json

from knos import ready
from knos_wanted import exports, metros


def report(with_city=True):
    cells = [{"lat": 36.17 + i * 0.01, "lon": -115.14, "affinity": 0.99 - i * 0.02} for i in range(4)] + [{"lat": 40.7, "lon": -74.0, "affinity": 0.5}]
    return {"hash": "cd" * 32, "idea": "a synthetic (desert) music festival", "made": "2026-10-22T22:09:40Z", "decision": {"verdict": "OPEN"},
            "matches": [{"id": "e1", "name": "X"}], "terms": metros.terms(cells) if with_city else None, "where": cells,
            "calls": [{"n": 1, "call": "GET /search", "what": "closest products", "params": {"query": "desert festival", "api_key": "never-shown", "take": 5},
                       "ms": 120, "cached": False, "body_digest": "SECRET-BODY 5 results", "out": "SECRET-BODY 5 results"},
                      {"n": 2, "call": "GET /v2/insights", "params": {"filter.type": "urn:heatmap"}, "cached": True, "body_digest": "SECRET-BODY cells"}]}


def test_the_calls_csv_holds_no_body_and_no_key():
    text = exports.csv_text(report())
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["n", "endpoint", "params", "ms", "cached", "fed"] and len(rows) == 3
    assert "SECRET-BODY" not in text and "never-shown" not in text and "api_key" not in text
    assert rows[1][:5] == ["1", "GET /search", "query=desert festival; take=5", "120", "no"] and rows[2][4] == "yes"


def test_the_ready_brief_json_and_its_hash():
    d = json.loads(exports.json_text(report()))
    assert d["ready"] is True and d["criteria_hash"] == ready.criteria_hash(d["brief"])
    none = json.loads(exports.json_text(report(with_city=False)))
    assert none["ready"] is False and none["brief"] is None and "no launch city" in none["why"]


def test_the_brief_pdf_is_one_page_with_the_cards_fields():
    b = exports.pdf(report(), "https://knos.onrender.com/r/" + "cd" * 8)
    assert b.startswith(b"%PDF-1.4") and b.rstrip().endswith(b"%%EOF") and b.count(b"/Type /Page ") == 1
    assert b"\\(desert\\)" in b and b"Pre-order target" in b and b"SECRET-BODY" not in b
    xref = int(b.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert b[xref:xref + 4] == b"xref"
