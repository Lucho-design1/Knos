"""The milestone check every referee host runs ITSELF before it signs (the referee here is code, run three times on
three hosts): it never signs a digest the coordinator hands it, only the one it recomputes.

A release request names: the commitment document (public: knos.ideas.commit), the stage, the maker's evidence URL.
The host reads the order from devnet, fetches the evidence page itself (https, public address, no redirects, size
and time limits), requires the commitment's claim id in it, builds the evidence exactly as knos.ideas.commit does
(review_evidence over the page), and recomputes the verdict digest the knos_pay program checks. The panel must be the
1-of-1 FROST group panel this host belongs to.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KIND = "knos-milestone-release"
MAX_EVIDENCE = 512_000
TIMEOUT_S = 10


class CheckFailed(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise CheckFailed("the evidence URL redirects; a referee reads only the page it was given")


def public_host(host: str | None) -> None:
    if not host:
        raise CheckFailed("evidence_url: no host")
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise CheckFailed("evidence_url: the host does not resolve") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise CheckFailed("evidence_url: not a public address")


def fetch(url: str, opener=None, resolve=public_host) -> bytes:
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https" or len(url) > 2000:
        raise CheckFailed("evidence_url: an https URL of at most 2,000 characters")
    resolve(u.hostname)
    op = opener or urllib.request.build_opener(_NoRedirect).open
    req = urllib.request.Request(url, headers={"User-Agent": "knos referee (FROST host) milestone check"})
    try:
        with op(req, timeout=TIMEOUT_S) as r:
            body = r.read(MAX_EVIDENCE + 1)
    except CheckFailed:
        raise
    except urllib.error.HTTPError as e:
        raise CheckFailed(f"the evidence URL answered HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CheckFailed(f"the evidence URL could not be read ({type(e).__name__})") from None
    if len(body) > MAX_EVIDENCE:
        raise CheckFailed(f"the evidence page is larger than {MAX_EVIDENCE:,} bytes")
    return body


def request(doc: dict, stage: str, evidence_url: str) -> dict:
    return {"kind": KIND, "doc": doc, "stage": stage, "verdict": "PASS", "evidence_url": evidence_url}


def milestone_digest(req: dict, group_key: str, led, *, fetcher=fetch) -> tuple[bytes, dict]:
    """(the verdict digest this host will sign, the evidence) or CheckFailed. Reads the chain and the page itself."""
    from solders.pubkey import Pubkey

    from ..ideas import IdeaError
    from ..ideas import commit as C
    from ..ideas import wanted as W
    from ..settle.v2 import pay
    if req.get("kind") != KIND or req.get("verdict") != "PASS":
        raise CheckFailed("not a milestone release request")
    doc, stage = req.get("doc") or {}, req.get("stage")
    try:
        C.plan_of(doc)                                   # the commitment file is the committed one
    except (IdeaError, KeyError, TypeError) as why:
        raise CheckFailed(f"the commitment does not check: {why}") from None
    panel = doc.get("panel") or {}
    if doc.get("judge") != "panel" or panel.get("m") != 1 or panel.get("keys") != [group_key]:
        raise CheckFailed("the commitment's panel is not this FROST group (1 of 1: the group key)")
    if stage not in (doc.get("orders") or {}):
        raise CheckFailed("stage: not a stage of this commitment")
    order, program = Pubkey.from_string(doc["orders"][stage]["order"]), Pubkey.from_string(doc["program"])
    data = led.account(order)
    o = pay.read_order(data) if data is not None else None
    if o is None:
        raise CheckFailed("the order is closed on chain (already released or refunded)")
    body = fetcher(req.get("evidence_url") or "")
    claim_id = doc["claim"]["id"]
    if claim_id.encode() not in body:
        raise CheckFailed(f"the evidence page does not contain the commitment's claim id {claim_id}")
    with tempfile.TemporaryDirectory() as d:
        page = Path(d) / "evidence"
        page.write_bytes(body)
        ev = C.review_evidence(doc, "referee_pass", True, page)
    digest = W.stage_digest(order, o, ev, C.payees_of(doc["payee"]), program)
    ev["page_sha256"] = hashlib.sha256(body).hexdigest()
    return digest, ev


def verdict_record(doc: dict, stage: str, ev: dict, digest: bytes, signature_hex: str, group_key: str, stamp: int) -> dict:
    """The aggregated FROST signature as an ordinary knos-idea-verdict record of the group key: knos.ideas.commit.release
    checks it (digest, signature, payee, order, funding) exactly like a single referee's verdict and sends it."""
    from ..ideas import commit as C
    return {"v": C.V, "kind": "knos-idea-verdict", "claim": doc["claim"]["id"], "commitment_hash": doc["commitment_hash"], "stage": stage,
            "oracle": doc["orders"][stage]["oracle"], "order": doc["orders"][stage]["order"], "stamp": stamp, "verdict": "PASS",
            "evidence_hash": ev["evidence_hash"], "evidence": {k: v for k, v in ev.items() if k != "mode"},
            "payees": C.payees_text(doc["payee"]), "key": group_key, "digest": digest.hex(), "sig": signature_hex,
            "signed": C.now(), "signed_by": "FROST 2-of-3 threshold signature of the referee group (knos.threshold)"}
