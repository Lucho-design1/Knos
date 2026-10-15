"""The small offline contract of knos.ideas: SOURCES, intake, orcid_ok and release_schedule (no network). Record keys
are named through knos.ideas.K, never spelled here."""
from __future__ import annotations

import pytest

from knos import ideas
from knos.ideas import FIELDS, K

MAT, CHEM, CS = FIELDS[16], FIELDS[5], FIELDS[6]
CARBERRY = "0000-0002-1825-0097"          # ORCID's public test record

# one OpenAlex work object, shaped as api.openalex.org/works returns it (synthetic fixture values)
WORK = {
    K.id: "https://openalex.org/W0000000001",
    K.title: "A synthetic fixture work about perovskite stability",
    K.is_retracted: False,
    K.primary_topic: {K.field: {K.display_name: MAT}},
    K.authorships: [{K.author: {K.display_name: "A", K.orcid: "https://orcid.org/" + CARBERRY}},
                    {K.author: {K.display_name: "B", K.orcid: None}}],
}


def person(title: str, **extra) -> dict:
    return {K.title: title, K.field: CHEM, K.by: "Ada", **extra}


def test_sources_name_every_kind_of_idea():
    want = {K.person, K.agent, K.player, K.openalex, K.arxiv, K.pubmed, K.europepmc, K.biorxiv, K.medrxiv, K.crossref,
            K.clinicaltrials, K.patent}
    assert set(ideas.SOURCES) >= want


def test_orcid_check_digit():
    assert ideas.orcid_ok(CARBERRY) and ideas.orcid_ok("https://orcid.org/" + CARBERRY)
    assert ideas.orcid_ok("0000-0001-5109-3700")
    assert ideas.orcid_ok("0000-0002-1694-233X")
    for bad in ("0000-0002-1825-0098", "0000-0002-1825-009", "", None, "https://orcid.org/abc", "0000000218250097"):
        assert not ideas.orcid_ok(bad)


def test_intake_of_a_person_and_an_openalex_work():
    p = ideas.intake(K.person, person("Idea one about binders", orcid=CARBERRY, github="octocat"))
    assert {K.source, K.id, K.title, K.field, K.retracted, K.researcher, K.hash} <= set(p)
    assert p[K.researcher] == [CARBERRY, "octocat"]
    assert p[K.retracted] is False and p[K.field] == CHEM
    again = ideas.intake(K.person, person("Idea one about binders", orcid=CARBERRY, github="octocat"))
    assert again[K.hash] == p[K.hash]
    other = ideas.intake(K.person, person("Idea two about binders", orcid=CARBERRY, github="octocat"))
    assert other[K.hash] != p[K.hash]
    with pytest.raises(ValueError):
        ideas.intake(K.person, person("x", orcid="0000-0002-1825-0098"))
    with pytest.raises(ValueError):
        ideas.intake("myspace", {K.title: "x"})
    w = ideas.intake(K.openalex, WORK)
    assert w[K.title] == WORK[K.title] and w[K.researcher] == [CARBERRY]
    assert w[K.field] == MAT
    assert w[K.retracted] is False
    assert ideas.intake(K.openalex, {**WORK, K.is_retracted: True})[K.retracted] is True
    for kind in (K.agent, K.player):
        got = ideas.intake(kind, {K.title: "An agent's claim about sorting", K.field: CS, K.by: "Claude"})
        assert got[K.source] == kind


def test_intake_flags_retractions_and_reads_trials():
    notice = {K.type: "retraction"}
    cr = ideas.intake(K.crossref, {K.DOI: "10.1/x", K.title: ["A fixture title"], K.updated_by: [notice]})
    assert cr[K.retracted] is True
    ct = ideas.intake(K.clinicaltrials, {K.protocolSection: {K.identificationModule: {K.nctId: "NCT00000001", K.briefTitle: "A fixture trial"},
                                                             K.statusModule: {K.overallStatus: "RECRUITING"}}})
    assert ct[K.id] == "NCT00000001"
    assert ct[K.field] == FIELDS[18]
    assert ct[K.retracted] is False


@pytest.mark.parametrize("total,percents", [(100, [20, 50, 30]), (40_000_000, [20, 30, 50]), (7, [33.4, 33.3, 33.3]), (10, [100]),
                                            (1, [50, 50]), (999, [10, 10, 10, 10, 10, 10, 10, 10, 10, 10])])
def test_release_schedule_sums_exactly_and_each_stage_is_within_one_unit(total, percents):
    got = ideas.release_schedule(total, percents)
    assert sum(got) == total and len(got) == len(percents) and all(isinstance(x, int) for x in got)
    assert all(abs(x - total * p / 100) < 1 for x, p in zip(got, percents))


def test_release_schedule_refuses_percents_not_summing_to_100():
    for bad in ([20, 50], [60, 60], [], [-10, 110]):
        with pytest.raises(ValueError):
            ideas.release_schedule(100, bad)
