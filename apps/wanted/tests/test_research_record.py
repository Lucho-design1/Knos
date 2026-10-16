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
    c = claim("Scurfin, a forkhead/winged-helix protein, is mutated in the scurfy mouse", field_name="Immunology and Microbiology",
              kind="literature", ids={"doi": "10.1038/83784"}, year=2001,
              retraction={"checked": True, "retracted": False, "notices": [], "via": "crossref updated-by"},
              extra={"topic": "T-cell and B-cell Immunology"})
    monkeypatch.setattr(sources, "get", lambda ref, f=None, enrich=True: c)
    return c


def test_card_quotes_the_result_cites_nobel_and_proposes_a_product(paper):
    card = research.research_card("10.1038/83784", fetcher=FakeFetch(), today=TODAY)
    assert card["proven_result"]["quote"].startswith("Here we report a device that harvests water")
    assert card["cited_by_count"] == 12000 and card["year"] == 2001 and card["retraction"]["retracted"] is False
    assert card["nobel"]["year"] == 2025 and card["nobel"]["url"].startswith("https://www.nobelprize.org/")
    assert card["no_product_evidence"]["said"] == "Several of these treatments are now undergoing clinical trials."
    assert card["product"] == card["nobel"]["enables"] and "nobelprize.org" in card["product_source"]
    edited = research.research_card("10.1038/83784", fetcher=FakeFetch(), product="a desert water maker", today=TODAY)
    assert edited["product"] == "a desert water maker" and edited["product_source"] == "edited by the maker"


def test_walls_are_flagged_only_with_evidence(paper):
    card = research.research_card("10.1038/83784", fetcher=FakeFetch(), today=TODAY)
    none = research.why_never_crossed(card, {"hash": "a" * 64, "matches": []}, TODAY)
    assert none[0]["flag"] is True and "25 years" in none[0]["evidence"] and "Nobel Physiology or Medicine 2025" in none[0]["evidence"]
    assert none[1]["flag"] is True and "Immunology" in none[1]["evidence"]
    assert none[2] == {"wall": "failed attempts", "flag": False, "evidence": "no evidence"}
    small = research.why_never_crossed(card, {"hash": "a" * 64, "matches": [{"name": "Tiny Water Co", "popularity": 0.1}]}, TODAY)
    assert small[0]["flag"] is False and small[2]["flag"] is True and "Tiny Water Co" in small[2]["evidence"]
    phys = {**card, "field": "Physics and Astronomy", "topic": "Optics", "topics": [], "product": "a faster camera"}
    assert research.why_never_crossed(phys, {"matches": []}, TODAY)[1]["flag"] is False


def test_product_table_and_generic_phrase():
    assert research.product_phrase("perovskite solar cells", None)[0] == "perovskite solar panels"
    p, why = research.product_phrase("quantum gravity spinfoam lattice", None)
    assert p.startswith("a product based on") and "edit it" in why
    with pytest.raises(research.ResearchError):
        research.research_card("")


def test_every_nobel_row_cites_its_press_release():
    rows = research.nobel_rows()
    assert len(rows) >= 4 and all(r["url"].startswith("https://") and r["said"] and r["doi"] for r in rows)
    assert all(r["url"].startswith("https://www.nobelprize.org/prizes/") for r in rows if r.get("nobel", True))
    top = next(r for r in rows if r["doi"] == "10.1038/nature16521")
    assert top["nobel"] is False and "fda.gov" in top["url"] and research.nobel_for(top["doi"])["enables"].startswith("a fitness watch")


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
    with pytest.raises(company.NotInRecord, match="marks this commitment released"):
        preorder.record_gate(rec)
    monkeypatch.setattr(company, "_record", lambda: None)
    with pytest.raises(company.NotInRecord):
        preorder.record_gate(rec)


def test_the_wake_page_pings_the_app_until_it_answers():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[3] / "web" / "wanted.html").read_text()
    assert "https://knos.onrender.com" in page and "/healthz" in page and "location.replace" in page
    assert "prefers-reduced-motion" in page and "Knos Wanted" not in page


def test_a_second_release_is_refused_by_sibyl_alone_over_http(monkeypatch):
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from knos_wanted import auth, server
    from knos_wanted.qloo_mcp import InProcess, Qloo
    from knos_wanted.qloo_rest import Client
    order = "R" * 43
    company.record_check(REP)
    company.record_lock(REP["hash"], order, 40, "sig")
    company.record_release(REP["hash"], order, ["s1", "s2"], "f" * 64)
    # this server's file still says "locked" and no chain or escrow key is configured: only Sibyl can refuse
    preorder._save({"order": order, "report": REP["hash"], "status": "locked", "claim_id": "knos-idea:" + "0" * 32, "units": 40})
    monkeypatch.setattr(preorder, "_need", lambda: (_ for _ in ()).throw(AssertionError("the chain path was reached")))
    st = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None), Client(key=""))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(st))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    tok = auth.guest("t")["token"]
    req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/milestone",
                                 json.dumps({"commitment": order, "evidence_url": "https://x.example/"}).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + tok})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=30)
    body = json.loads(e.value.read())
    httpd.shutdown()
    assert e.value.code == 409 and body["error"] == "refused: the Knos Record (Sibyl) marks this commitment released"
    assert body["refused_by"] == "Knos Record (Sibyl)"
