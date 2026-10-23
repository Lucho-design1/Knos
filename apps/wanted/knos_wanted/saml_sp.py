"""Knos as its own SAML service provider for the TEST identity providers (enterprise.test_idps: mocksaml.com, and the
self-hosted Keycloak realm). Self-hosted, so no server-to-server call stands between a sign-in and the IdP: the
separate Jackson service answered this server HTTP 429 (TASK-WORLD T10), and a company's own IdP still goes through
Jackson (enterprise.sso_start).

    GET  /auth/sso?tenant=knos-test   ->  an AuthnRequest (HTTP-Redirect binding) to the IdP's sign-in page
    POST /auth/sso/acs                ->  the IdP's signed SAMLResponse (HTTP-POST binding), checked here, -> a session
    GET  /auth/sso/metadata           ->  this service provider's metadata (its entity id and ACS address)

The response is accepted only when its XML signature verifies against the IdP's own certificate (read from the IdP's
metadata), and only from the element that signature covers (no signature wrapping): status Success, an assertion
within its time window, for this audience, sent to this ACS, in answer to a request this server made in the last 10
minutes. The email is the NameID (or an email attribute). Needs the app's `saml` extra (signxml, lxml).
"""
from __future__ import annotations

import base64
import datetime as dt
import secrets
import threading
import time
import urllib.parse
import urllib.request
import zlib
from xml.sax.saxutils import escape

NS = {"md": "urn:oasis:names:tc:SAML:2.0:metadata", "ds": "http://www.w3.org/2000/09/xmldsig#",
      "samlp": "urn:oasis:names:tc:SAML:2.0:protocol", "saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
SKEW_S = 120
_pending: dict[str, tuple[float, dict]] = {}
_meta: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


class SAMLError(ValueError):
    pass


def available() -> bool:
    try:
        import lxml.etree  # noqa: F401
        import signxml  # noqa: F401
    except ImportError:
        return False
    return True


def _parse(xml: bytes):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
    return etree.fromstring(xml, parser)


def idp(metadata_url: str, opener=None) -> dict:
    """The IdP's sign-in address and signing certificate, from its metadata (cached an hour)."""
    with _lock:
        hit = _meta.get(metadata_url)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
    try:
        req = urllib.request.Request(metadata_url, headers={"Accept": "application/xml",          # Python's default agent is refused
                                                            "User-Agent": "knos-saml-sp (+https://knos.onrender.com/auth/sso/metadata)"})
        with (opener or urllib.request.urlopen)(req, timeout=30) as r:
            root = _parse(r.read(1_000_000))
    except OSError as e:
        raise SAMLError(f"the test identity provider's metadata could not be read ({type(e).__name__}); try again in a minute") from None
    sso = root.find(".//md:IDPSSODescriptor/md:SingleSignOnService[@Binding='%s']" % REDIRECT, NS)
    certs = [c.text.strip() for c in root.findall(".//md:IDPSSODescriptor/md:KeyDescriptor/ds:KeyInfo/ds:X509Data/ds:X509Certificate", NS)
             if c.text and c.text.strip()]
    if sso is None or not certs:
        raise SAMLError("the identity provider's metadata names no HTTP-Redirect sign-in or no signing certificate")
    got = {"sso": sso.get("Location"), "certs": ["".join(c.split()) for c in certs], "entity": root.get("entityID")}
    with _lock:
        _meta[metadata_url] = (time.time(), got)
    return got


def entity(base_url: str) -> str:
    return base_url.rstrip("/") + "/auth/sso/metadata"


def acs(base_url: str) -> str:
    return base_url.rstrip("/") + "/auth/sso/acs"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def start(tenant: str, metadata_url: str, base_url: str, next_page: str = "/", opener=None) -> str:
    """The IdP sign-in address carrying a fresh AuthnRequest (deflated, base64, as the Redirect binding says)."""
    i = idp(metadata_url, opener)
    rid = "_" + secrets.token_hex(20)
    req = (f'<samlp:AuthnRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" ID="{rid}" Version="2.0" '
           f'IssueInstant="{_now()}" Destination="{escape(i["sso"])}" AssertionConsumerServiceURL="{escape(acs(base_url))}" '
           f'ProtocolBinding="{POST}"><saml:Issuer>{escape(entity(base_url))}</saml:Issuer>'
           f'<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>'
           f'</samlp:AuthnRequest>')
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = base64.b64encode(c.compress(req.encode()) + c.flush()).decode()
    relay = secrets.token_urlsafe(24)
    with _lock:
        now = time.time()
        for k in [k for k, (t, _) in _pending.items() if now - t > 600]:
            _pending.pop(k)
        _pending[relay] = (now, {"id": rid, "tenant": tenant, "metadata": metadata_url, "next": next_page})
    sep = "&" if "?" in i["sso"] else "?"
    return i["sso"] + sep + urllib.parse.urlencode({"SAMLRequest": packed, "RelayState": relay})


def _time(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def finish(saml_response: str, relay: str, base_url: str, opener=None) -> dict:
    """Check the IdP's response; returns {"tenant", "email", "next"} or raises SAMLError naming what failed."""
    from signxml import XMLVerifier
    from signxml.exceptions import InvalidInput, InvalidSignature
    with _lock:
        got = _pending.pop(relay or "", None)
    if got is None or time.time() - got[0] > 600:
        raise SAMLError("this sign-in expired or was not started here: start again")
    p = got[1]
    try:
        raw = base64.b64decode(saml_response or "", validate=False)
    except ValueError:
        raise SAMLError("the identity provider's answer is not base64") from None
    if not raw or len(raw) > 500_000:
        raise SAMLError("the identity provider sent no answer")
    certs = idp(p["metadata"], opener)["certs"]
    signed = None
    for cert in certs:
        try:
            signed = XMLVerifier().verify(_parse(raw), x509_cert=cert).signed_xml
            break
        except (InvalidSignature, InvalidInput):
            continue
    if signed is None:
        raise SAMLError("the identity provider's signature does not verify")
    tag = signed.tag.split("}")[-1]
    if tag == "Response":
        st = signed.find("samlp:Status/samlp:StatusCode", NS)
        if st is None or not st.get("Value", "").endswith(":Success"):
            raise SAMLError("the identity provider did not sign you in")
        a = signed.find("saml:Assertion", NS)
    elif tag == "Assertion":
        a = signed
    else:
        raise SAMLError("the signature covers neither the response nor its assertion")
    if a is None:
        raise SAMLError("the signed response holds no assertion")
    now = time.time()
    cond = a.find("saml:Conditions", NS)
    nb, na = (_time(cond.get("NotBefore")), _time(cond.get("NotOnOrAfter"))) if cond is not None else (None, None)
    if (nb and now + SKEW_S < nb) or (na and now - SKEW_S >= na):
        raise SAMLError("the identity provider's answer is out of its time window")
    audiences = [x.text.strip() for x in a.findall("saml:Conditions/saml:AudienceRestriction/saml:Audience", NS) if x.text]
    if audiences and entity(base_url) not in audiences:
        raise SAMLError("the identity provider's answer is for another service")
    sc = a.find("saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData", NS)
    if sc is None or sc.get("Recipient") != acs(base_url) or sc.get("InResponseTo") != p["id"]:
        raise SAMLError("the identity provider's answer is not for this sign-in")
    if _time(sc.get("NotOnOrAfter")) and now - SKEW_S >= _time(sc.get("NotOnOrAfter")):
        raise SAMLError("the identity provider's answer expired")
    nid = a.find("saml:Subject/saml:NameID", NS)
    email = (nid.text or "").strip().lower() if nid is not None else ""
    if "@" not in email:
        for at in a.findall("saml:AttributeStatement/saml:Attribute", NS):
            if "mail" in (at.get("Name") or "").lower():
                v = at.find("saml:AttributeValue", NS)
                email = (v.text or "").strip().lower() if v is not None else ""
                break
    if "@" not in email or len(email) > 254:
        raise SAMLError("the identity provider sent no email")
    return {"tenant": p["tenant"], "email": email, "next": p["next"]}


def metadata(base_url: str) -> bytes:
    """This service provider's metadata: what a company's IdP admin registers."""
    return (f'<?xml version="1.0"?><md:EntityDescriptor xmlns:md="{NS["md"]}" entityID="{escape(entity(base_url))}">'
            f'<md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol" AuthnRequestsSigned="false" '
            f'WantAssertionsSigned="true"><md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>'
            f'<md:AssertionConsumerService Binding="{POST}" Location="{escape(acs(base_url))}" index="0"/></md:SPSSODescriptor>'
            f'</md:EntityDescriptor>').encode()
