"""The research card (landmark result -> product phrase -> walls) on SYNTHETIC fixtures, and the Knos Record (Sibyl)
read before any money moves."""
import datetime as dt

import pytest

from knos_wanted import company, preorder, research

TODAY = dt.date(2026, 10, 16)


class FakeFetch:
    """OpenAlex's work answer for one DOI (SYNTHETIC numbers, shaped like OpenAlex)."""

    def __init__(self, cited=12000, abstract="Water scarcity is a global problem. Here we report a device that harvests water from air using sunlight."):
        words = abstract.split()
        self.work = {"id": "https://openalex.org/W1", "publication_year": 2017, "cited_by_count": cited, "is_retracted": False,
                     "abstract_inverted_index": {w: [i for i, x in enumerate(words) if x == w] for w in set(words)},
                     "topics": [{"display_name": "Metal-Organic Frameworks: Synthesis and Applications"}],
                     "keywords": [{"display_name": "Water harvesting"}], "concepts": [{"display_name": "Chemistry"}]}

    def json(self, url):
        return self.work, "fixture"


@pytest.fixture
def paper(monkeypatch):
    from knos.ideas import claim, sources
    c = claim("Water harvesting from air with metal-organic frameworks powered by natural sunlight", field_name="Chemistry",
              kind="literature", ids={"doi": "10.1126/science.aam8743"}, year=2017,
              retraction={"checked": True, "retracted": False, "notices": [], "via": "crossref updated-by"},
              extra={"topic": "Metal-Organic Frameworks: Synthesis and Applications"})
    monkeypatch.setattr(sources, "get", lambda ref, f=None, enrich=True: c)
    return c


def test_card_quotes_the_result_cites_nobel_and_proposes_a_product(paper):
    card = research.research_card("10.1126/science.aam8743", fetcher=FakeFetch(), today=TODAY)
    assert card["proven_result"]["quote"].startswith("Here we report a device that harvests water")
    assert card["cited_by_count"] == 12000 and card["year"] == 2017 and card["retraction"]["retracted"] is False
    assert card["nobel"]["year"] == 2025 and card["nobel"]["url"].startswith("https://www.nobelprize.org/")
    assert card["product"] == card["nobel"]["enables"] and "nobelprize.org" in card["product_source"]
    edited = research.research_card("10.1126/science.aam8743", fetcher=FakeFetch(), product="a desert water maker", today=TODAY)
    assert edited["product"] == "a desert water maker" and edited["product_source"] == "edited by the maker"


def test_walls_are_flagged_only_with_evidence(paper):
    card = research.research_card("10.1126/science.aam8743", fetcher=FakeFetch(), today=TODAY)
    none = research.why_never_crossed(card, {"hash": "a" * 64, "matches": []}, TODAY)
    assert none[0]["flag"] is True and "9 years" in none[0]["evidence"] and "Nobel Chemistry 2025" in none[0]["evidence"]
    assert none[1]["flag"] is False and none[2] == {"wall": "failed attempts", "flag": False, "evidence": "no evidence"}
    small = research.why_never_crossed(card, {"hash": "a" * 64, "matches": [{"name": "Tiny Water Co", "popularity": 0.1}]}, TODAY)
    assert small[0]["flag"] is False and small[2]["flag"] is True and "Tiny Water Co" in small[2]["evidence"]
    med = {**card, "field": "Medicine", "topic": "T cell therapy"}
    assert research.why_never_crossed(med, {"matches": []}, TODAY)[1]["flag"] is True


def test_product_table_and_generic_phrase():
    assert research.product_phrase("perovskite solar cells", None)[0] == "perovskite solar panels"
    p, why = research.product_phrase("quantum gravity spinfoam lattice", None)
    assert p.startswith("a product based on") and "edit it" in why
    with pytest.raises(research.ResearchError):
        research.research_card("")


def test_every_nobel_row_cites_its_press_release():
    rows = research.nobel_rows()
    assert len(rows) >= 6 and all(r["url"].startswith("https://www.nobelprize.org/prizes/") and r["said"] and r["doi"] for r in rows)


# ---- the Record (Sibyl) is read before money moves ------------------------------------------------------------------
pytest.importorskip("sibyl_memory_client")

REP = {"hash": "b" * 64, "idea": "x", "label": "LIVE Qloo data", "calls": [{"call": "GET /search"}],
       "decision": {"verdict": "OPEN", "target_units": 100, "reserve_units": 30}}


def test_check_is_written_and_read_back_from_sibyl():
    assert company.record_check(REP)["recorded"] is True
    held = company.record_state(REP["hash"])
    assert held["verdict"] == "OPEN" and held["target_units"] == 100 and held["preorders"]["units"] == 0
    with pytest.raises(company.NotInRecord):
        company.record_state("c" * 64)


def test_a_preorder_needs_the_report_in_sibyl(monkeypatch):
    with pytest.raises(company.NotInRecord, match="not in the Knos Record"):
        preorder.lock({**REP, "hash": "d" * 64}, 10, "guest: t")           # never recorded: nothing locks
    company.record_check({**REP, "hash": "e" * 64, "decision": {**REP["decision"], "target_units": 50}})
    with pytest.raises(company.NotInRecord, match="this target"):
        preorder.lock({**REP, "hash": "e" * 64}, 10, "guest: t")           # Sibyl holds another target: refused
    monkeypatch.setattr(company, "_record", lambda: None)                  # Sibyl absent
    with pytest.raises(company.NotInRecord, match="not available"):
        preorder.lock(REP, 10, "guest: t")


def test_release_gate_reads_the_preorder_and_refuses_a_second_release(monkeypatch):
    company.record_check(REP)
    rec = {"report": REP["hash"], "order": "O" * 43}
    with pytest.raises(company.NotInRecord, match="no pre-order"):
        preorder.record_gate(rec)
    assert company.record_lock(REP["hash"], rec["order"], 40, "sig")["recorded"] is True
    held = preorder.record_gate(rec)
    assert held["preorders"] == {"orders": 1, "units": 40, "list": [rec["order"]]}
    assert preorder.reserve_status(REP)["met"] is True and preorder.reserve_status(REP)["source"] == "Knos Record (Sibyl)"
    assert company.record_release(REP["hash"], rec["order"], ["s1", "s2"], "f" * 64)["recorded"] is True
    with pytest.raises(company.NotInRecord, match="already holds this commitment as released"):
        preorder.record_gate(rec)
    monkeypatch.setattr(company, "_record", lambda: None)
    with pytest.raises(company.NotInRecord):
        preorder.record_gate(rec)


def test_the_wake_page_pings_the_app_until_it_answers():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[3] / "docs" / "wanted.html").read_text()
    assert "https://knos.onrender.com" in page and "/healthz" in page and "location.replace" in page
    assert "prefers-reduced-motion" in page and "Knos Wanted" not in page
