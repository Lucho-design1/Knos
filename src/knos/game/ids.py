"""Permanent identifiers for a graduated result: a Zenodo DOI and Software Heritage identifiers (SWHIDs).

Zenodo (sandbox only here): the deposit API, read 14 Oct 2026 at https://developers.zenodo.org/ . Base
https://sandbox.zenodo.org/api/ ; every call carries `Authorization: Bearer <token>` (scopes deposit:write and
deposit:actions); POST deposit/depositions makes a draft whose links.bucket takes the file (PUT <bucket>/<name>);
PUT deposit/depositions/<id> sets {"metadata": {...}}; POST deposit/depositions/<id>/actions/publish publishes. The
sandbox's DOIs use the test prefix 10.5072 and the sandbox "can be cleaned at anytime" (same page). The token is read
from KNOS_ZENODO_SANDBOX_TOKEN only, sent only in that header, never logged or stored. Without it: a FIXTURE, labelled,
with no DOI (a DOI is never invented).

Software Heritage: the save-code-now API, read 14 Oct 2026 at https://archive.softwareheritage.org/api/1/origin/save/doc/
: POST (or GET for the status) https://archive.softwareheritage.org/api/1/origin/save/<visit_type>/url/<origin_url>/ ;
well-known forges such as GitHub are "immediately accepted"; the reply carries save_request_status, save_task_status,
and snapshot_swhid once a visit happened. The page names no authentication for it; the API answered anonymously on
14 Oct 2026 with X-RateLimit-Limit 120. The SWHID of one file is intrinsic, `swh:1:cnt:<sha1 of "blob <n>\\0" + bytes>`
(the git blob hash), so Knos computes it locally; it resolves in the archive once an archived origin holds that file.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ZENODO = "https://sandbox.zenodo.org/api/"
ZENODO_ENV = "KNOS_ZENODO_SANDBOX_TOKEN"
SWH = "https://archive.softwareheritage.org/api/1/"
FIXTURE = "FIXTURE (synthetic, not a Zenodo response)"


class IdError(RuntimeError):
    pass


def swhid_content(data: bytes) -> str:
    """The intrinsic SWHID of a file's bytes (core SWHID, object type cnt)."""
    return "swh:1:cnt:" + hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _http(method: str, url: str, headers: dict | None = None, body: bytes | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method=method, headers={"Accept": "application/json", "User-Agent": "knos", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - fixed https hosts
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as why:
        try:
            got = json.loads(why.read() or b"{}")
        except ValueError:
            got = {}
        return why.code, got
    except (urllib.error.URLError, TimeoutError, ValueError) as why:
        raise IdError(f"{method} {url.split('?')[0]}: {type(why).__name__}") from None


def swh_save(origin_url: str, *, visit_type: str = "git", http=_http, post: bool = True) -> dict:
    """Ask Software Heritage to archive an origin (POST), or read the request's status (post=False). LIVE, no key."""
    if not origin_url.startswith("https://"):
        raise IdError("origin_url: an https URL")
    url = SWH + f"origin/save/{visit_type}/url/{origin_url}/"
    code, got = http("POST" if post else "GET", url)
    if isinstance(got, list):
        got = got[0] if got else {}
    keep = ("id", "request_url", "origin_url", "visit_type", "save_request_date", "save_request_status", "save_task_status",
            "visit_date", "visit_status", "snapshot_swhid", "note")
    return {"mode": "live", "http": code, **{k: got.get(k) for k in keep if k in got},
            "error": None if code < 400 else (got.get("reason") or got.get("exception") or f"HTTP {code}")}


def zenodo_deposit(metadata: dict, files: dict[str, bytes], *, token: str | None = None, http=_http, publish: bool = True) -> dict:
    """A deposition on the Zenodo SANDBOX: draft, files, metadata, publish. FIXTURE without a token."""
    token = token if token is not None else os.environ.get(ZENODO_ENV, "")
    plan = {"metadata": metadata, "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    if not token:
        return {"mode": "fixture", "label": FIXTURE, "doi": None, "why": f"{ZENODO_ENV} is not set: no deposition was made", "would_deposit": plan}
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    code, d = http("POST", ZENODO + "deposit/depositions", auth, b"{}")
    if code >= 400 or "id" not in d:
        return {"mode": "live", "doi": None, "error": f"create: HTTP {code}"}
    bucket = (d.get("links") or {}).get("bucket")
    for name, data in files.items():
        c, _ = http("PUT", f"{bucket}/{urllib.parse.quote(name)}", {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}, data)
        if c >= 400:
            return {"mode": "live", "doi": None, "id": d["id"], "error": f"upload {name}: HTTP {c}"}
    c, _ = http("PUT", ZENODO + f"deposit/depositions/{d['id']}", auth, json.dumps({"metadata": metadata}).encode())
    if c >= 400:
        return {"mode": "live", "doi": None, "id": d["id"], "error": f"metadata: HTTP {c}"}
    if not publish:
        return {"mode": "live", "doi": None, "id": d["id"], "draft": True}
    c, pub = http("POST", ZENODO + f"deposit/depositions/{d['id']}/actions/publish", auth, b"")
    if c >= 400:
        return {"mode": "live", "doi": None, "id": d["id"], "error": f"publish: HTTP {c}"}
    return {"mode": "live", "sandbox": True, "id": d["id"], "doi": pub.get("doi"), "record_url": (pub.get("links") or {}).get("html"),
            "note": "Zenodo SANDBOX: test DOI prefix 10.5072, may be cleaned at any time"}


def metadata(title: str, description: str, creators: list[str], keywords=()) -> dict:
    """Zenodo deposit metadata (upload_type software)."""
    return {"title": title, "upload_type": "software", "description": description,
            "creators": [{"name": c} for c in creators] or [{"name": "Knos"}], "keywords": list(keywords)}
