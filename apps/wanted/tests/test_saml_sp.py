"""knos_wanted.saml_sp: Knos as the SAML service provider for the test IdPs. A throwaway IdP key signs the assertions
here; a valid one becomes an email, and a tampered, foreign, late or replayed one is refused."""
import base64
import datetime as dt
import io
import urllib.parse
import zlib

import pytest

pytest.importorskip("signxml")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402
from lxml import etree  # noqa: E402
from signxml import XMLSigner  # noqa: E402

from knos_wanted import saml_sp  # noqa: E402

BASE = "https://knos.example"
META = "https://idp.example/metadata"


def _idp():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test idp")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1)).sign(key, hashes.SHA256()))
    return key, cert


KEY, CERT = _idp()
PEM = CERT.public_bytes(serialization.Encoding.PEM).decode()
B64 = "".join(PEM.splitlines()[1:-1])
METADATA = (f'<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            f'entityID="https://idp.example"><md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
            f'<md:KeyDescriptor use="signing"><ds:KeyInfo><ds:X509Data><ds:X509Certificate>{B64}</ds:X509Certificate></ds:X509Data>'
            f'</ds:KeyInfo></md:KeyDescriptor><md:SingleSignOnService Binding="{saml_sp.REDIRECT}" Location="https://idp.example/sso"/>'
            f'</md:IDPSSODescriptor></md:EntityDescriptor>').encode()


def opener(req, timeout=None):
    return io.BytesIO(METADATA)


def _request_id(url: str) -> tuple[str, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    xml = zlib.decompress(base64.b64decode(q["SAMLRequest"][0]), -15)
    return etree.fromstring(xml).get("ID"), q["RelayState"][0]


def _response(rid: str, audience: str = saml_sp.entity(BASE), recipient: str = saml_sp.acs(BASE), minutes: int = 5,
              email: str = "ada@example.com") -> etree._Element:
    now = dt.datetime.now(dt.timezone.utc)
    t = lambda d: (now + dt.timedelta(minutes=d)).strftime("%Y-%m-%dT%H:%M:%SZ")   # noqa: E731
    xml = (f'<samlp:Response xmlns:samlp="{saml_sp.NS["samlp"]}" xmlns:saml="{saml_sp.NS["saml"]}" ID="_r1" Version="2.0" '
           f'IssueInstant="{t(0)}"><samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
           f'<saml:Assertion ID="_a1" Version="2.0" IssueInstant="{t(0)}"><saml:Issuer>https://idp.example</saml:Issuer>'
           f'<saml:Subject><saml:NameID>{email}</saml:NameID><saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
           f'<saml:SubjectConfirmationData InResponseTo="{rid}" Recipient="{recipient}" NotOnOrAfter="{t(minutes)}"/></saml:SubjectConfirmation>'
           f'</saml:Subject><saml:Conditions NotBefore="{t(-1)}" NotOnOrAfter="{t(minutes)}"><saml:AudienceRestriction>'
           f'<saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction></saml:Conditions></saml:Assertion></samlp:Response>')
    return etree.fromstring(xml.encode())


def _signed(root) -> str:
    out = XMLSigner().sign(root, key=KEY, cert=PEM)
    return base64.b64encode(etree.tostring(out)).decode()


def _fresh():
    saml_sp._meta.clear()
    url = saml_sp.start("knos-test", META, BASE, "/companies", opener=opener)
    assert url.startswith("https://idp.example/sso?SAMLRequest=")
    return _request_id(url)


def test_a_signed_answer_to_our_request_is_an_email():
    rid, relay = _fresh()
    got = saml_sp.finish(_signed(_response(rid)), relay, BASE, opener=opener)
    assert got == {"tenant": "knos-test", "email": "ada@example.com", "next": "/companies"}
    with pytest.raises(saml_sp.SAMLError, match="expired or was not started"):            # one use only
        saml_sp.finish(_signed(_response(rid)), relay, BASE, opener=opener)


@pytest.mark.parametrize("bad, why", [
    (lambda rid: _response(rid, audience="https://other.example"), "another service"),
    (lambda rid: _response(rid, recipient="https://other.example/acs"), "not for this sign-in"),
    (lambda rid: _response("_someone_else"), "not for this sign-in"),
    (lambda rid: _response(rid, minutes=-10), "time window"),
])
def test_a_foreign_late_or_misdirected_answer_is_refused(bad, why):
    rid, relay = _fresh()
    with pytest.raises(saml_sp.SAMLError, match=why):
        saml_sp.finish(_signed(bad(rid)), relay, BASE, opener=opener)


def test_a_tampered_answer_does_not_verify():
    rid, relay = _fresh()
    doc = etree.fromstring(base64.b64decode(_signed(_response(rid))))
    nid = doc.find(".//{%s}NameID" % saml_sp.NS["saml"])
    nid.text = "mallory@example.com"
    with pytest.raises(saml_sp.SAMLError, match="signature does not verify"):
        saml_sp.finish(base64.b64encode(etree.tostring(doc)).decode(), relay, BASE, opener=opener)


def test_the_metadata_names_this_acs():
    m = saml_sp.metadata(BASE)
    assert saml_sp.acs(BASE).encode() in m and saml_sp.entity(BASE).encode() in m
