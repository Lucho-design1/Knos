"""Step 1, idea in: every research source read through its official API and normalised to one Claim record, offline.

The bodies come from tests/fixtures/ideas/recorded-fixture.json (FIXTURE: responses recorded from the official APIs on
14 Oct 2026, abstracts removed). No test here reaches the network: urlopen is replaced by one that fails. Record keys
are named through knos.ideas.K, never spelled here."""
from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from knos import ideas
from knos.ideas import FIELDS, K, identity, sources
from knos.ideas.http import Fetcher, NoFixture

FIXTURE = Path(__file__).parent / "fixtures" / "ideas" / "recorded-fixture.json"
BIO, MAT, MED, ENG, CS = FIELDS[2], FIELDS[16], FIELDS[18], FIELDS[12], FIELDS[6]
CARBERRY = "0000-0002-1825-0097"          # ORCID's public test record (Josiah Carberry)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for k in ideas.ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no live API call in tests")))
    monkeypatch.setenv(ideas.FIXTURES_ENV, str(FIXTURE))


def f() -> Fetcher:
    return Fetcher()


def test_the_fixture_file_says_it_is_a_fixture():
    assert "FIXTURE" in FIXTURE.read_text(encoding="utf-8")[:300]


def test_a_pubmed_claim_has_its_ids_its_openalex_field_and_a_clean_retraction_check():
    c = sources.get("pmid:42806035", f())
    ids = c[K.ids]
    assert ids[K.pmid] == "42806035"
    assert ids[K.doi] == "10.1038/s41467-026-77241-5" and ids[K.openalex].startswith("W")
    assert c[K.field] == BIO
    r = c[K.retraction]
    assert r[K.checked] is True and r[K.retracted] is False and c[K.risk] == []
    assert c[K.label].startswith("FIXTURE")
    assert {s[K.source] for s in c[K.sources]} == {K.pubmed, K.openalex}
    assert ideas.check(c) is c and c[K.id].startswith(ideas.PREFIX)


def test_an_arxiv_claim_takes_its_field_from_the_category():
    c = sources.get("arxiv:1606.00335", f())
    assert c[K.field] == MAT and c[K.ids] == {K.arxiv: "1606.00335", K.doi: "10.1016/j.solmat.2016.09.012"}
    assert c[K.arxiv_category].startswith("cond-mat")
    assert c[K.links] == ["https://arxiv.org/abs/1606.00335"]


def test_a_clinical_trial_is_a_claim_in_medicine_with_its_status():
    c = sources.get("NCT04718792", f())
    t = c[K.trial]
    assert c[K.field] == MED and c[K.ids] == {K.nct: "NCT04718792"} and t[K.has_results] is False
    assert t[K.phases] == ["PHASE2"]


def test_a_retracted_paper_is_flagged_as_a_risk_signal_from_retraction_watch():
    c = sources.get("doi:10.1016/s0140-6736(97)11096-0", f())
    r = c[K.retraction]
    assert r[K.retracted] is True and K.retracted in c[K.risk] and K.corrected in c[K.risk]
    assert any(n[K.type] == "retraction" for n in r[K.notices])
    assert all(n[K.source] == "retraction-watch" for n in r[K.notices])


def test_a_preprint_and_its_journal_version_and_a_europe_pmc_record():
    c = sources.get("biorxiv:10.1101/2020.03.22.002386", f())
    assert c[K.ids][K.biorxiv] == "10.1101/2020.03.22.002386"
    assert c[K.published_doi] == "10.1038/s41586-020-2286-9"
    e = sources.get("pmcid:PMC7116826", f())
    assert e[K.ids][K.pmid] == "33057194"
    assert e[K.ids][K.pmcid] == "PMC7116826"
    # the same paper read twice is the same idea id (its DOI)
    assert sources.get("pmcid:PMC7116826", f())[K.id] == e[K.id]


def test_search_returns_claims_and_patents_are_a_labelled_fixture_without_the_key():
    trials = sources.search(K.clinicaltrials, "psilocybin alcohol", f(), limit=2)
    assert len(trials) == 2 and all(t[K.ids][K.nct].startswith("NCT") for t in trials)
    papers = sources.search(K.arxiv, "perovskite solar stability", f(), limit=2)
    assert len(papers) == 2 and all(p[K.ids][K.arxiv] for p in papers)
    pat = sources.get("uspto:00000001", Fetcher(fixtures={}))
    assert pat[K.sources][0][K.mode] == K.fixture
    assert "synthetic" in pat[K.fixture_label] and ideas.ENVS[2] in pat[K.fixture_label]
    assert pat[K.field] == ENG and pat[K.label].startswith("FIXTURE")
    st = {r[K.source]: r for r in sources.status()}
    assert st[K.uspto][K.mode] == K.fixture and st[K.crossref][K.mode] == K.live and len(st) == len(sources.SOURCES)


def test_references_name_their_source_and_a_missing_body_is_refused():
    assert sources.parse_ref("https://doi.org/10.1/x") == (K.crossref, "10.1/x")
    assert sources.parse_ref("nct04718792") == (K.clinicaltrials, "NCT04718792")
    assert sources.parse_ref("2212.11279") == (K.arxiv, "2212.11279")
    assert sources.parse_ref("33057194") == (K.pubmed, "33057194")
    with pytest.raises(ideas.IdeaError):
        sources.parse_ref("myspace:1")
    with pytest.raises(NoFixture):
        sources.get("pmid:1", Fetcher(fixtures={}))


def test_researchers_by_orcid_and_github():
    o = identity.who("https://orcid.org/" + CARBERRY, f())
    assert o[K.kind] == K.orcid and o[K.name] == "Josiah Carberry"
    assert "not signed in" in o[K.verified]
    g = identity.who("github:drexthealpha", f())
    assert g[K.id] == 142920951 and g[K.kind] == K.github
    with pytest.raises(ideas.IdeaError):
        identity.parse("orcid:0000-0002-1825-0098")          # wrong check digit


def test_an_idea_from_a_person_a_player_and_an_agent():
    by = identity.short(identity.who("orcid:" + CARBERRY, f()))
    p = ideas.person("A perovskite cell keeps 95% efficiency after 1000 h damp heat.", by=by)
    assert p[K.field] == MAT and p[K.origin][K.kind] == K.person and p[K.origin][K.by][K.id] == CARBERRY
    assert p[K.label].startswith("STATED")
    g = ideas.person("A folding move lowers the energy of protein X below -300.", kind=K.player, field_name=BIO.lower())
    assert g[K.field] == BIO and g[K.origin][K.kind] == K.player
    a = ideas.person("An agent claims a faster sort for nearly sorted arrays.", kind=K.agent, by={K.kind: K.agent, K.name: "Claude"})
    assert a[K.field] == CS
    with pytest.raises(ideas.IdeaError):
        ideas.person("short")
    with pytest.raises(ideas.IdeaError):
        ideas.person("A claim in a field that does not exist.", field_name="Alchemy")
    changed = dict(a, statement="something else entirely")
    with pytest.raises(ideas.IdeaError):
        ideas.check(changed)
    assert len(FIELDS) == 26
