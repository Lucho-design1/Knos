"""The research sources an idea can come from: each read through its OFFICIAL API, normalised to one Claim record.

`get(ref)` reads one work/trial/patent; `search(source, words)` lists claims. A reference names its source:

    doi:10.1038/s41586-020-2832-5     Crossref (with the Retraction Watch check), then OpenAlex for the field
    pmid:33057194                     PubMed (NCBI E-utilities esummary)
    pmcid:PMC7116826 / epmc:...       Europe PMC REST search
    arxiv:2212.11279                  arXiv API (Atom)
    biorxiv:10.1101/2020.03.22.002386 bioRxiv API details (medrxiv:... the same for medRxiv)
    openalex:W3035965352              OpenAlex works
    NCT04368728 / nct:NCT04368728     ClinicalTrials.gov API v2
    uspto:16123456                    USPTO Open Data Portal (needs USPTO_ODP_API_KEY; else a labelled FIXTURE)

Every record whose DOI is known is checked against Crossref's Retraction Watch data (the work's `updated-by` entries
with `source: retraction-watch`): a retraction, correction or expression of concern becomes a risk signal on the
record (knos.ideas, `risk`), never a silent drop.

Access rules, read 14 Oct 2026 (SOURCES[...]["rules"] carries each with its URL; docs/reference/IDEAS.md the table):
keyless and free for all but patents. Keys, all optional except USPTO: OPENALEX_API_KEY (raises OpenAlex's daily
budget; keyless budget is $0.10/day per IP), NCBI_API_KEY (3 -> 10 requests/s), USPTO_ODP_API_KEY (required).
KNOS_CONTACT_EMAIL, if set, joins Crossref's polite pool and is NCBI's `email`.
"""
from __future__ import annotations

import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any
from datetime import date, timedelta

from . import IdeaError, claim, field, merge, now
from .http import FetchError, Fetcher, contact

SOURCES: dict[str, dict[str, Any]] = {
    "openalex": {"name": "OpenAlex", "api": "https://api.openalex.org/works", "key": "OPENALEX_API_KEY (optional)",
                 "rules": "no key: 10 req/s and a shared daily budget ($0.10/day per IP, header x-ratelimit-limit-usd); a single work is free, a search $0.001; free key 30 req/s; data CC0 "
                          "(help.openalex.org/api/authentication, read 14 Oct 2026; live probe 14 Oct 2026)"},
    "arxiv": {"name": "arXiv", "api": "https://export.arxiv.org/api/query", "key": None,
              "rules": "no key; one request every 3 s, one connection at a time; metadata CC0 (info.arxiv.org/help/api/tou.html, read 14 Oct 2026)"},
    "pubmed": {"name": "PubMed (NCBI E-utilities)", "api": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/", "key": "NCBI_API_KEY (optional)",
               "rules": "3 req/s without a key, 10 with one; send tool= and email=; show NCBI's disclaimer (ncbi.nlm.nih.gov/books/NBK25497, read 14 Oct 2026; "
                        "live probe header x-ratelimit-limit: 3, 14 Oct 2026)"},
    "europepmc": {"name": "Europe PMC", "api": "https://www.ebi.ac.uk/europepmc/webservices/rest/search", "key": None,
                  "rules": "open, no key; no published rate figure (Knos keeps 5 req/s); live probe 200, 14 Oct 2026"},
    "biorxiv": {"name": "bioRxiv", "api": "https://api.biorxiv.org/details/biorxiv/", "key": None,
                "rules": "open, no key; details by DOI or date interval (30 per page), pubs = preprint -> journal links (api.biorxiv.org, read 14 Oct 2026); no keyword search"},
    "medrxiv": {"name": "medRxiv", "api": "https://api.biorxiv.org/details/medrxiv/", "key": None,
                "rules": "as bioRxiv (same API, server 'medrxiv')"},
    "crossref": {"name": "Crossref (+ Retraction Watch)", "api": "https://api.crossref.org/works", "key": None,
                 "rules": "public pool 5 req/s, 1 at a time; polite pool (mailto) 10 req/s, 3 at a time; metadata free to reuse; retractions in `updated-by` "
                          "with source retraction-watch (crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication, "
                          "crossref.org/documentation/retrieve-metadata/retraction-watch, read 14 Oct 2026)"},
    "clinicaltrials": {"name": "ClinicalTrials.gov API v2", "api": "https://clinicaltrials.gov/api/v2/studies", "key": None,
                       "rules": "open, no key; no rate figure in the OpenAPI spec (clinicaltrials.gov/api/oas/v2); ~5 req/s observed without 429 (14 Oct 2026)"},
    "uspto": {"name": "USPTO Open Data Portal (patents)", "api": "https://api.uspto.gov/api/v1/patent/applications/search", "key": "USPTO_ODP_API_KEY (required)",
              "rules": "free key from data.uspto.gov (USPTO.gov account with MFA), header X-API-KEY; burst 1 (no parallel calls), 4-15 req/s, 5M metadata calls/week "
                       "(data.uspto.gov/apis/api-rate-limits, read 14 Oct 2026); PatentsView moved into ODP on 20 Mar 2026 "
                       "(uspto.gov bulletin 18 Mar 2026). Live probe 14 Oct 2026: 401 without a key, 403 with a wrong one. EPO OPS needs registration "
                       "(probe 403 fair use) and Lens a token (probe 401): not used."},
}

# the patent FIXTURE answered while USPTO_ODP_API_KEY is missing: SYNTHETIC, shaped from the ODP response structure
# (patentFileWrapperDataBag[].applicationMetaData, field names as patent_client's ODP model reads them). Not a real record.
USPTO_FIXTURE: dict[str, Any] = {
    "label": "FIXTURE (synthetic, shaped from the USPTO ODP response structure; not a real API response)",
    "count": 1,
    "patentFileWrapperDataBag": [{
        "applicationNumberText": "00000001",
        "applicationMetaData": {"inventionTitle": "Encapsulated perovskite solar module retaining efficiency under damp heat (synthetic example)",
                                "filingDate": "2026-01-01", "applicationStatusDescriptionText": "Docketed New Case - Ready for Examination",
                                "cpcClassificationBag": ["H10K30/50"], "firstApplicantName": "Example Applicant (synthetic)"}}],
}

_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_NCT = re.compile(r"^NCT\d{8}$", re.I)
_ARXIV = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?)$", re.I)


def parse_ref(ref: str) -> tuple[str, str]:
    """(source, id) of a reference; a bare DOI, NCT id, PMID number or arXiv id is recognised as such."""
    r = (ref or "").strip()
    for p in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if r.lower().startswith(p):
            r = "doi:" + r[len(p):]
    if ":" in r and not r.lower().startswith("10."):
        src, _, ident = r.partition(":")
        src = src.lower()
        alias = {"doi": "crossref", "pmid": "pubmed", "pmcid": "europepmc", "epmc": "europepmc", "nct": "clinicaltrials",
                 "ct": "clinicaltrials", "w": "openalex"}
        src = alias.get(src, src)
        if src not in SOURCES:
            raise IdeaError(f"unknown source {src!r}: one of doi, pmid, pmcid, arxiv, biorxiv, medrxiv, openalex, nct, uspto")
        return src, ident.strip()
    if _DOI.match(r):
        return "crossref", r
    if _NCT.match(r):
        return "clinicaltrials", r.upper()
    if r.isdigit():
        return "pubmed", r
    if _ARXIV.match(r):
        return "arxiv", r
    if re.match(r"^W\d+$", r):
        return "openalex", r
    raise IdeaError(f"name the source: doi:..., pmid:..., arxiv:..., biorxiv:..., nct:..., openalex:W..., uspto:... (got {ref!r})")


def _src(source: str, ident: str, url: str, mode: str) -> dict:
    return {"source": source, "id": ident, "url": url, "mode": mode, "read": now()}


def _q(v: str) -> str:
    return urllib.parse.quote(v, safe="")


# ---- Crossref + Retraction Watch -------------------------------------------------------------------------------
def _crossref_url(path: str) -> str:
    sep = "&" if "?" in path else "?"
    mail = contact()
    return f"https://api.crossref.org/{path}" + (f"{sep}mailto={_q(mail)}" if mail else "")


def retraction(f: Fetcher, doi: str, work: dict | None = None) -> dict:
    """Crossref's Retraction Watch data for one DOI: the work's `updated-by` entries (retraction, correction,
    expression of concern, ...) whose source is retraction-watch, plus any notice Crossref members deposited."""
    mode = f.mode
    if work is None:
        try:
            got, mode = f.json(_crossref_url(f"works/{_q(doi)}"))
            work = got.get("message") or {}
        except FetchError as e:
            return {"checked": False, "retracted": False, "notices": [], "via": "crossref", "error": str(e)}
    notices = []
    for u in work.get("updated-by") or []:
        dp = ((u.get("updated") or {}).get("date-parts") or [[None]])[0]
        notices.append({"doi": u.get("DOI"), "type": str(u.get("type", "")).lower(), "source": u.get("source"),
                        "date": "-".join(str(x) for x in dp if x is not None) or None, "record_id": u.get("record-id")})
    retracted = any(n["type"] in ("retraction", "withdrawal", "removal") for n in notices)
    title = " ".join(work.get("title") or [])
    if title.upper().startswith("RETRACTED"):
        retracted = True
    return {"checked": True, "retracted": retracted, "notices": notices, "via": "Crossref (Retraction Watch data)", "mode": mode, "read": now()}


def crossref(f: Fetcher, doi: str) -> dict:
    url = _crossref_url(f"works/{_q(doi)}")
    got, mode = f.json(url)
    w = got.get("message") or {}
    title = " ".join(w.get("title") or []) or doi
    dp = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
    subjects = w.get("subject") or []
    c = claim(title, field_name=field(text=title + " " + " ".join(subjects)), kind="literature",
              ids={"doi": (w.get("DOI") or doi).lower()}, sources=[_src("crossref", doi, url, mode)], retraction=retraction(f, doi, w),
              links=[f"https://doi.org/{doi}"], year=dp[0] if dp and isinstance(dp[0], int) else None,
              venue=" ".join(w.get("container-title") or []) or w.get("publisher"))
    return c


# ---- OpenAlex ----------------------------------------------------------------------------------------------------
_OA_SELECT = "id,doi,title,publication_year,primary_topic,is_retracted,ids,primary_location"


def _oa_url(path: str, query: dict) -> str:
    k = os.environ.get("OPENALEX_API_KEY")
    q = {**query, **({"api_key": k} if k else {})}
    return f"https://api.openalex.org/{path}?" + urllib.parse.urlencode(q)


# OpenAlex level-0 concepts -> Knos's 26 fields (the topic taxonomy's own names)
_LEVEL0 = {"materials science": "Materials Science", "chemistry": "Chemistry", "physics": "Physics and Astronomy",
           "biology": "Biochemistry, Genetics and Molecular Biology", "medicine": "Medicine", "computer science": "Computer Science",
           "mathematics": "Mathematics", "psychology": "Psychology", "engineering": "Engineering", "geology": "Earth and Planetary Sciences",
           "environmental science": "Environmental Science", "economics": "Economics, Econometrics and Finance",
           "business": "Business, Management and Accounting", "political science": "Social Sciences", "sociology": "Social Sciences",
           "geography": "Social Sciences", "philosophy": "Arts and Humanities", "history": "Arts and Humanities", "art": "Arts and Humanities"}


def _concepts(f: Fetcher, oid: str) -> list:
    """The work's OpenAlex concepts (a second free single-work read); [] when it cannot be read (offline fixtures)."""
    if not oid:
        return []
    try:
        got, _ = f.json(_oa_url(f"works/{oid}", {"select": "id,concepts"}))
    except FetchError:
        return []
    return got.get("concepts") or []


_TOPIC_WORDS = {"materials": "Materials Science", "chemistry": "Chemistry", "chemical": "Chemistry", "physics": "Physics and Astronomy",
                "engineering": "Engineering"}


def openalex_field(w: dict, concepts: list | None = None) -> tuple[str | None, str]:
    """The field of an OpenAlex work: its primary topic's field, unless the work's own level-0 concepts do not support
    that field at all; then the field the topic's name names ("High-pressure geophysics and materials" -> Materials
    Science), else the top level-0 concept's. OpenAlex files Dias's superconductor papers under Earth and Planetary
    Sciences though no concept of theirs is geology; a perovskite solar cell under Engineering though its top concept is
    Materials science. Without concepts (offline), the primary topic's field stands."""
    topic = w.get("primary_topic") or {}
    pf = (topic.get("field") or {}).get("display_name")
    name = str(topic.get("display_name") or "")
    level0 = [(_LEVEL0.get(str(c.get("display_name") or "").lower()), c.get("score") or 0) for c in (concepts or []) if c.get("level") == 0]
    if not pf or not level0 or any(f == pf and sc >= 0.3 for f, sc in level0):
        return pf, f"OpenAlex primary topic '{name}'" if pf else "no OpenAlex topic"
    words = name.lower().replace(",", " ").split()
    named = [f for word, f in _TOPIC_WORDS.items() if word in words and f != pf]
    if named:
        return named[0], f"OpenAlex topic '{name}' names it; no concept of the work supports '{pf}'"
    top = sorted((x for x in level0 if x[0] and x[1] >= 0.5), key=lambda x: -x[1])
    if top:
        return top[0][0], f"OpenAlex top concept; no concept of the work supports '{pf}'"
    return pf, f"OpenAlex primary topic '{name}'"


def _oa_claim(f: Fetcher, w: dict, url: str, mode: str, check_retraction: bool = True) -> dict:
    ids = w.get("ids") or {}
    doi = (w.get("doi") or ids.get("doi") or "").replace("https://doi.org/", "").lower() or None
    pmid = (ids.get("pmid") or "").rstrip("/").split("/")[-1] or None
    pmcid = (ids.get("pmcid") or "").rstrip("/").split("/")[-1] or None
    oid = (w.get("id") or "").split("/")[-1]
    topic = w.get("primary_topic") or {}
    fname, fwhy = openalex_field(w, _concepts(f, oid))
    title = w.get("title") or w.get("display_name") or oid
    try:
        fld = field(fname) if fname else field(text=title)
    except IdeaError:
        fld = field(text=title)
    r = retraction(f, doi) if (doi and check_retraction) else {"checked": False, "retracted": False, "notices": [], "via": None}
    if w.get("is_retracted"):
        r = {**r, "retracted": True, "openalex_is_retracted": True}
    venue = (((w.get("primary_location") or {}).get("source")) or {}).get("display_name")
    return claim(title, field_name=fld, kind="literature", ids={"openalex": oid, "doi": doi, "pmid": pmid, "pmcid": pmcid},
                 sources=[_src("openalex", oid, url.split("&api_key=")[0].split("?api_key=")[0], mode)], retraction=r,
                 links=[x for x in (w.get("id"), f"https://doi.org/{doi}" if doi else None) if x], year=w.get("publication_year"), venue=venue,
                 extra={"field_source": fwhy, "topic": topic.get("display_name"), "subfield": (topic.get("subfield") or {}).get("display_name")})


def openalex(f: Fetcher, ident: str) -> dict:
    path = f"works/{ident}" if re.match(r"^W\d+$", ident) else f"works/doi:{ident}"
    url = _oa_url(path, {"select": _OA_SELECT})
    got, mode = f.json(url)
    return _oa_claim(f, got, url, mode)


# ---- arXiv -------------------------------------------------------------------------------------------------------
_A = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _arxiv_entries(f: Fetcher, url: str) -> list[dict]:
    body, mode = f.get(url, {"Accept": "application/atom+xml"})
    root = ET.fromstring(body)
    out = []
    for e in root.findall("a:entry", _A):
        aid = (e.findtext("a:id", "", _A) or "").rsplit("/abs/", 1)[-1]
        if not aid or e.findtext("a:title", None, _A) is None:
            continue
        prim = e.find("arxiv:primary_category", _A)
        cat = prim.get("term") if prim is not None else ""
        doi = e.findtext("arxiv:doi", "", _A) or None
        title = " ".join((e.findtext("a:title", "", _A) or "").split())
        year = int((e.findtext("a:published", "", _A) or "0000")[:4]) or None
        base = re.sub(r"v\d+$", "", aid)
        r = retraction(f, doi) if doi else {"checked": False, "retracted": False, "notices": [], "via": None}
        comment = e.findtext("arxiv:comment", "", _A) or ""
        if "withdrawn" in comment.lower():
            r = {**r, "retracted": True, "arxiv_withdrawn": True}
        out.append(claim(title, field_name=field(arxiv=cat, text=title), kind="literature", ids={"arxiv": base, "doi": doi},
                         sources=[_src("arxiv", base, url, mode)], retraction=r, links=[f"https://arxiv.org/abs/{base}"], year=year,
                         venue="arXiv " + cat if cat else "arXiv", extra={"arxiv_category": cat}))
    return out


def arxiv(f: Fetcher, ident: str) -> dict:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": ident})
    got = _arxiv_entries(f, url)
    if not got:
        raise IdeaError(f"arXiv has no paper {ident}")
    return got[0]


# ---- PubMed (E-utilities) and Europe PMC ---------------------------------------------------------------------------
def _eutils(path: str, q: dict) -> str:
    extra: dict[str, str] = {"tool": "knos"}
    if contact():
        extra["email"] = contact() or ""
    if os.environ.get("NCBI_API_KEY"):
        extra["api_key"] = os.environ["NCBI_API_KEY"]
    return f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/{path}?" + urllib.parse.urlencode({**q, **extra})


def _strip_key(url: str) -> str:
    return re.sub(r"[&?]api_key=[^&]*", "", url)


def _pubmed_claims(f: Fetcher, pmids: list[str]) -> list[dict]:
    url = _eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    got, mode = f.json(url)
    res = got.get("result") or {}
    out = []
    for pid in res.get("uids", []):
        d = res.get(pid) or {}
        art = {a.get("idtype"): a.get("value") for a in d.get("articleids") or []}
        doi = (art.get("doi") or "").lower() or None
        title = d.get("title") or pid
        types = [str(t).lower() for t in d.get("pubtype") or []]
        r = retraction(f, doi) if doi else {"checked": False, "retracted": False, "notices": [], "via": None}
        if "retracted publication" in types:
            r = {**r, "retracted": True, "pubmed_retracted_publication": True}
        out.append(claim(title, field_name=field(text=title + " " + (d.get("source") or "")), kind="literature",
                         ids={"pmid": pid, "doi": doi, "pmcid": art.get("pmc")}, sources=[_src("pubmed", pid, _strip_key(url), mode)], retraction=r,
                         links=[f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"], year=int(str(d.get("pubdate", "0"))[:4] or 0) or None,
                         venue=d.get("fulljournalname") or d.get("source"),
                         extra={"ncbi_disclaimer": "NCBI data: see https://www.ncbi.nlm.nih.gov/home/about/policies/ (no endorsement by NCBI or NLM)"}))
    return out


def pubmed(f: Fetcher, pmid: str) -> dict:
    got = _pubmed_claims(f, [pmid])
    if not got:
        raise IdeaError(f"PubMed has no record {pmid}")
    return got[0]


def _epmc_claim(f: Fetcher, d: dict, url: str, mode: str) -> dict:
    doi = (d.get("doi") or "").lower() or None
    title = str(d.get("title") or d.get("id"))
    r = retraction(f, doi) if doi else {"checked": False, "retracted": False, "notices": [], "via": None}
    src = d.get("source")
    return claim(title, field_name=field(text=title), kind="literature",
                 ids={"pmid": d.get("pmid"), "pmcid": d.get("pmcid"), "doi": doi, **({"epmc": f"{src}:{d.get('id')}"} if src == "PPR" else {})},
                 sources=[_src("europepmc", f"{src}:{d.get('id')}", url, mode)], retraction=r,
                 links=[f"https://europepmc.org/article/{src}/{d.get('id')}"], year=int(d.get("pubYear") or 0) or None,
                 venue=d.get("journalTitle") or ("preprint" if src == "PPR" else None))


def europepmc(f: Fetcher, ident: str) -> dict:
    q = f"PMCID:{ident}" if ident.upper().startswith("PMC") else (f"EXT_ID:{ident} AND SRC:MED" if ident.isdigit() else ident)
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": q, "format": "json", "resultType": "lite", "pageSize": 1})
    got, mode = f.json(url)
    rows = ((got.get("resultList") or {}).get("result")) or []
    if not rows:
        raise IdeaError(f"Europe PMC has no record for {ident}")
    return _epmc_claim(f, rows[0], url, mode)


# ---- bioRxiv / medRxiv -----------------------------------------------------------------------------------------------
def _rxiv_claim(f: Fetcher, server: str, d: dict, url: str, mode: str) -> dict:
    doi = (d.get("doi") or "").lower()
    pub = d.get("published")
    published = pub if pub and pub != "NA" else None
    r = retraction(f, published) if published else {"checked": False, "retracted": False, "notices": [], "via": None}
    return claim(d.get("title") or doi, field_name=field(subject=d.get("category") or "", text=d.get("title") or ""), kind="literature",
                 ids={server: doi, "doi": published or doi}, sources=[_src(server, doi, url, mode)], retraction=r,
                 links=[f"https://www.{server}.org/content/{doi}v{d.get('version', 1)}"], year=int(str(d.get("date", "0"))[:4]) or None,
                 venue=server, extra={"subject": d.get("category"), "published_doi": published, "preprint_version": d.get("version")})


def rxiv(f: Fetcher, ident: str, server: str = "biorxiv") -> dict:
    url = f"https://api.biorxiv.org/details/{server}/{ident}/na/json"
    got, mode = f.json(url)
    rows = got.get("collection") or []
    if not rows:
        raise IdeaError(f"{server} has no preprint {ident}")
    return _rxiv_claim(f, server, rows[-1], url, mode)             # the latest version


def rxiv_published(f: Fetcher, ident: str, server: str = "biorxiv") -> dict:
    """bioRxiv's `pubs` endpoint: the journal DOI a preprint was published as (a milestone oracle), or none."""
    url = f"https://api.biorxiv.org/pubs/{server}/{ident}/na/json"
    got, mode = f.json(url)
    rows = got.get("collection") or []
    return {"published_doi": rows[0].get("published_doi") if rows else None, "journal": rows[0].get("published_journal") if rows else None,
            "url": url, "mode": mode, "read": now()}


# ---- ClinicalTrials.gov ------------------------------------------------------------------------------------------
_CT_FIELDS = "NCTId,BriefTitle,OfficialTitle,OverallStatus,HasResults,Condition,Phase,StartDate,LeadSponsorName,StudyType"
_CT_RISK = {"WITHDRAWN": "withdrawn-trial", "TERMINATED": "terminated-trial", "SUSPENDED": "suspended-trial"}


def _ct_claim(d: dict, url: str, mode: str) -> dict:
    p = d.get("protocolSection") or {}
    idm, st, cm, dm = (p.get(k) or {} for k in ("identificationModule", "statusModule", "conditionsModule", "designModule"))
    nct = str(idm.get("nctId") or "")
    title = idm.get("briefTitle") or idm.get("officialTitle") or nct
    status = st.get("overallStatus")
    start = ((st.get("startDateStruct") or {}).get("date") or "")[:4]
    c = claim(title, field_name="Psychology" if "psych" in " ".join(cm.get("conditions") or []).lower() else "Medicine", kind="literature",
              ids={"nct": nct}, sources=[_src("clinicaltrials", nct, url, mode)],
              links=[f"https://clinicaltrials.gov/study/{nct}"], year=int(start) if start.isdigit() else None,
              venue=((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name"),
              extra={"trial": {"status": status, "has_results": bool(d.get("hasResults")), "conditions": cm.get("conditions") or [],
                               "phases": dm.get("phases") or [], "type": dm.get("studyType")}})
    if status in _CT_RISK:
        c["risk"].append(_CT_RISK[status])
        from . import record_hash
        c["hash"] = record_hash(c)
    return c


def clinicaltrials(f: Fetcher, nct: str) -> dict:
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct.upper()}?" + urllib.parse.urlencode({"fields": _CT_FIELDS})
    got, mode = f.json(url)
    return _ct_claim(got, url, mode)


# ---- USPTO Open Data Portal --------------------------------------------------------------------------------------
def _uspto_rows(got: dict) -> list[dict]:
    rows = []
    for b in got.get("patentFileWrapperDataBag") or got.get("patentBag") or []:
        m = {**b, **(b.get("applicationMetaData") or {})}
        rows.append(m)
    return rows


def _uspto_claim(m: dict, url: str, mode: str, label: str | None) -> dict:
    app = str(m.get("applicationNumberText") or "")
    cpc = (m.get("cpcClassificationBag") or [""])[0]
    title = str(m.get("inventionTitle") or app)
    c = claim(title, field_name=field(cpc=cpc) if cpc else field(text=title), kind="literature",
              ids={"patent": f"US{app}", **({"patent_number": m.get("patentNumber")} if m.get("patentNumber") else {})},
              sources=[_src("uspto", app, url, mode)], links=[f"https://data.uspto.gov/patent-file-wrapper/search/details/{app}"],
              year=int(str(m.get("filingDate", "0"))[:4]) or None, venue="USPTO",
              extra={"patent": {"status": m.get("applicationStatusDescriptionText"), "cpc": m.get("cpcClassificationBag") or [],
                                "applicant": m.get("firstApplicantName")}, **({"fixture_label": label} if label else {})})
    return c


def _uspto(f: Fetcher, url: str) -> tuple[dict, str, str | None]:
    k = os.environ.get("USPTO_ODP_API_KEY")
    if not k:
        return USPTO_FIXTURE, "fixture", USPTO_FIXTURE["label"] + " (USPTO_ODP_API_KEY missing)"
    got, mode = f.json(url, {"X-API-KEY": k})
    return got, mode, None


def uspto(f: Fetcher, app: str) -> dict:
    app = app.upper().removeprefix("US").replace("/", "").replace(",", "")
    url = f"https://api.uspto.gov/api/v1/patent/applications/{app}"
    got, mode, label = _uspto(f, url)
    rows = _uspto_rows(got)
    if not rows:
        raise IdeaError(f"USPTO has no application {app}")
    return _uspto_claim(rows[0], url, mode, label)


# ---- one door --------------------------------------------------------------------------------------------------------
_GET = {"crossref": crossref, "openalex": openalex, "arxiv": arxiv, "pubmed": pubmed, "europepmc": europepmc,
        "biorxiv": lambda f, i: rxiv(f, i, "biorxiv"), "medrxiv": lambda f, i: rxiv(f, i, "medrxiv"),
        "clinicaltrials": clinicaltrials, "uspto": uspto}


def refield(c: dict, f: Fetcher) -> dict:
    """The claim with its field from OpenAlex (by DOI, or an arXiv paper's DataCite DOI 10.48550/arXiv.<id>), so a
    paper gets the same field from `get` and from `search`; unchanged when OpenAlex cannot be read."""
    from . import claim as _claim
    ids = c.get("ids", {})
    doi = ids.get("doi") or (f"10.48550/arxiv.{ids['arxiv']}" if ids.get("arxiv") else None)
    if not doi:
        return c
    try:
        got, _ = f.json(_oa_url(f"works/doi:{doi}", {"select": _OA_SELECT}))
    except FetchError:
        return c
    fld, why = openalex_field(got, _concepts(f, (got.get("id") or "").split("/")[-1]))
    if not fld or fld == c["field"]:
        return c
    std = {"v", "id", "field", "statement", "origin", "ids", "sources", "retraction", "risk", "links", "year", "venue", "label", "hash"}
    risk_extra = [r for r in c.get("risk", []) if r not in ("retracted", "corrected", "expression-of-concern")]
    out = _claim(c["statement"], field_name=fld, kind=c["origin"]["kind"], by=c["origin"].get("by"), ids=ids, sources=c["sources"],
                 retraction=c["retraction"], links=c["links"], year=c.get("year"), venue=c.get("venue"),
                 extra={**{k: v for k, v in c.items() if k not in std}, "field_source": why})
    if risk_extra:
        from . import record_hash
        out["risk"] += [r for r in risk_extra if r not in out["risk"]]
        out["hash"] = record_hash(out)
    return out


def get(ref: str, f: Fetcher | None = None, enrich: bool = True) -> dict:
    """One claim from a reference. `enrich`: a DOI read from Crossref is also read from OpenAlex (field, topic, ids),
    the two joined into one record."""
    f = f or Fetcher()
    src, ident = parse_ref(ref)
    c = _GET[src](f, ident)
    if enrich and src == "arxiv":
        c = refield(c, f)
    doi = c["ids"].get("doi")
    if enrich and doi and src not in ("openalex", "arxiv", "uspto"):
        try:
            url = _oa_url(f"works/doi:{doi}", {"select": _OA_SELECT})
            got, mode = f.json(url)
            oa = _oa_claim(f, got, url, mode, check_retraction=False)
            if src == "crossref":
                c = merge(oa, c)                   # OpenAlex's statement, field and topic; Crossref's retraction check
            else:                                  # the source's own words; OpenAlex's field (one taxonomy for all science)
                c = merge(c, oa)
                from . import claim as _claim
                std = {"v", "id", "field", "statement", "origin", "ids", "sources", "retraction", "risk", "links", "year", "venue", "label", "hash"}
                c = _claim(c["statement"], field_name=oa["field"], kind="literature", ids=c["ids"], sources=c["sources"], retraction=c["retraction"],
                           links=c["links"], year=c.get("year"), venue=c.get("venue"), extra={k: v for k, v in c.items() if k not in std})
        except (FetchError, IdeaError):
            pass
    return c


def search(source: str, words: str, f: Fetcher | None = None, limit: int = 5) -> list[dict]:
    """Claims matching `words` in one source (biorxiv/medrxiv: titles of the last 7 days' preprints), each filed
    under the field OpenAlex gives it (the same field `get` gives)."""
    f = f or Fetcher()
    got = _search(source, words, f, limit)
    return got if source in ("openalex", "uspto") else [refield(c, f) for c in got]


def _search(source: str, words: str, f: Fetcher, limit: int) -> list[dict]:
    limit = max(1, min(int(limit), 25))
    words = " ".join(str(words).split())[:300]
    if not words:
        raise IdeaError("search words: some text")
    if source == "openalex":
        url = _oa_url("works", {"search": words, "per_page": limit, "select": _OA_SELECT})
        got, mode = f.json(url)
        return [_oa_claim(f, w, url, mode, check_retraction=False) for w in got.get("results") or []]
    if source == "arxiv":
        return _arxiv_entries(f, "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": "all:" + words, "start": 0, "max_results": limit, "sortBy": "relevance"}))
    if source == "pubmed":
        got, _ = f.json(_eutils("esearch.fcgi", {"db": "pubmed", "term": words, "retmax": limit, "retmode": "json"}))
        ids = ((got.get("esearchresult") or {}).get("idlist")) or []
        return _pubmed_claims(f, ids) if ids else []
    if source == "europepmc":
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": words, "format": "json", "resultType": "lite", "pageSize": limit})
        got, mode = f.json(url)
        return [_epmc_claim(f, d, url, mode) for d in ((got.get("resultList") or {}).get("result")) or []]
    if source in ("biorxiv", "medrxiv"):
        end = date.today()
        url = f"https://api.biorxiv.org/details/{source}/{(end - timedelta(days=7)).isoformat()}/{end.isoformat()}/0/json"
        got, mode = f.json(url)
        want = [w.lower() for w in words.split()]
        rows = [d for d in got.get("collection") or [] if all(w in (d.get("title") or "").lower() for w in want)]
        return [_rxiv_claim(f, source, d, url, mode) for d in rows[:limit]]
    if source == "crossref":
        url = _crossref_url("works?" + urllib.parse.urlencode({"query": words, "rows": limit}))
        got, mode = f.json(url)
        out = []
        for w in (got.get("message") or {}).get("items") or []:
            doi = (w.get("DOI") or "").lower()
            title = " ".join(w.get("title") or []) or doi
            dp = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
            out.append(claim(title, field_name=field(text=title), kind="literature", ids={"doi": doi},
                             sources=[_src("crossref", doi, url, mode)], retraction=retraction(f, doi, w), links=[f"https://doi.org/{doi}"],
                             year=dp[0] if dp and isinstance(dp[0], int) else None, venue=" ".join(w.get("container-title") or []) or None))
        return out
    if source == "clinicaltrials":
        url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({"query.term": words, "pageSize": limit, "fields": _CT_FIELDS})
        got, mode = f.json(url)
        return [_ct_claim(d, url, mode) for d in got.get("studies") or []]
    if source == "uspto":
        url = "https://api.uspto.gov/api/v1/patent/applications/search?" + urllib.parse.urlencode({"q": words, "limit": limit})
        got, mode, label = _uspto(f, url)
        return [_uspto_claim(m, url, mode, label) for m in _uspto_rows(got)[:limit]]
    raise IdeaError(f"unknown source {source!r}: one of {', '.join(SOURCES)}")


def status() -> list[dict]:
    """Each source: live or fixture right now, and which key would change that."""
    out = []
    for k, s in SOURCES.items():
        need = s["key"] and "required" in s["key"]
        env = (s["key"] or "").split(" ")[0]
        have = bool(env and os.environ.get(env))
        out.append({"source": k, "name": s["name"], "api": s["api"], "mode": "fixture" if need and not have else "live",
                    "key": s["key"], "key_set": have if env else None, "rules": s["rules"]})
    return out
