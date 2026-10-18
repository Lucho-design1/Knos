"""Companies (knos_wanted.enterprise): SSO through SAML Jackson (fake Jackson, real PKCE), the Squads v4 multisig per
company, ERP exports (and a real hledger import when hledger is installed); provenance (in-toto/DSSE, C2PA); and the
OpenAPI document built from the server's own route tables."""
import base64
import csv
import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import urllib.parse

import pytest
from solders.keypair import Keypair

from knos_wanted import enterprise, openapi, product_routes, provenance, server, valley

OWNER = {"sub": "pk:owner", "kind": "passkey", "label": "owner"}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sso_through_jackson_with_pkce(monkeypatch):
    monkeypatch.setenv("KNOS_SSO_URL", "https://jackson.test")
    monkeypatch.setenv("KNOS_SSO_CLIENT_SECRET", "verifier-secret")
    monkeypatch.setenv("KNOS_SSO_API_KEY", "api-key")
    calls = []

    def opener(req, timeout=60):
        calls.append((req.get_method(), req.full_url, req.data))
        u = urllib.parse.urlparse(req.full_url)
        if u.path == "/api/v1/sso" and req.get_method() == "GET":
            return Resp(b"[]")
        if u.path == "/api/v1/sso":
            assert b"mocksaml.com" in req.data and req.headers["Authorization"] == "Api-Key api-key"
            return Resp(b"{}")
        if u.path == "/api/oauth/token":
            form = urllib.parse.parse_qs(req.data.decode())
            ch = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
            assert ch == challenge[0] and form["client_secret"] == ["verifier-secret"]
            return Resp(json.dumps({"access_token": "at"}).encode())
        if u.path == "/api/oauth/userinfo":
            return Resp(json.dumps({"email": "Jane@Example.com", "requested": {"tenant": "knos-test"}}).encode())
        raise AssertionError(req.full_url)

    url = enterprise.sso_start("knos-test", "https://knos.example", opener=opener)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    challenge = q["code_challenge"]
    assert url.startswith("https://jackson.test/api/oauth/authorize") and q["client_id"] == ["tenant=knos-test&product=knos"]
    assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == ["https://knos.example/auth/sso/callback"]
    s = enterprise.sso_callback("code1", q["state"][0], opener=opener)
    assert s["kind"] == "sso" and s["label"] == "jane@example.com (knos-test)" and s["token"]
    from knos_wanted import auth
    assert auth.who("Bearer " + s["token"])["kind"] == "sso"
    with pytest.raises(enterprise.SSOError):
        enterprise.sso_callback("code1", q["state"][0], opener=opener)         # a state is used once


def test_sso_off_without_config(monkeypatch):
    monkeypatch.delenv("KNOS_SSO_URL", raising=False)
    assert enterprise.sso_config()["enabled"] is False
    with pytest.raises(enterprise.SSOError):
        enterprise.sso_start("x", "https://knos.example")


def test_squads_create_v2_encoding():
    a, b = str(Keypair().pubkey()), str(Keypair().pubkey())
    d = enterprise.create_v2_data([a, b], 2, memo="Knos company: Acme")
    assert d[:8] == hashlib.sha256(b"global:multisig_create_v2").digest()[:8]
    assert d[8] == 0 and struct.unpack("<H", d[9:11])[0] == 2 and struct.unpack("<I", d[11:15])[0] == 2
    assert d[15 + 32] == 7 and d.endswith(b"Knos company: Acme")
    k = Keypair().pubkey()
    p1, p2 = enterprise.squads_pdas(k), enterprise.squads_pdas(k)
    assert p1 == p2 and p1["multisig"] != p1["vault"]
    with pytest.raises(ValueError):
        enterprise.company_multisig_tx("Acme", [a, b], 3, a)
    with pytest.raises(ValueError):
        enterprise.company_multisig_tx("Acme", [a, b], 2, str(Keypair().pubkey()))   # the creator is a member


def _project_with_orders():
    p = valley.create_project(OWNER, "vendor_deliverable", "Survey export")
    pr = valley.project(p["id"])
    for i, st in enumerate(("released", "refunded", "locked")):
        oid = str(Keypair().pubkey())
        valley._save("orders", oid, {"order": oid, "project": p["id"], "milestone": "delivered", "units": 10 + i, "unit_price": 1,
                                     "kind": "funder", "funder": str(Keypair().pubkey()), "status": st, "made": "2026-10-17T00:00:00Z",
                                     "signatures": {"lock": "L" * 88, "referee_2_pass": "R" * 88} if st == "released" else {"lock": "L" * 88},
                                     "paid_to": {"maker": str(Keypair().pubkey())} if st == "released" else None})
        pr["milestones"][1]["fundings"].append(oid)
    valley._save("projects", p["id"], pr)
    return p["id"]


def test_erp_exports():
    pid = _project_with_orders()
    for fmt in enterprise.FORMATS:
        body, ctype = enterprise.export(pid, fmt)
        rows = list(csv.reader(io.StringIO(body)))
        assert ctype.startswith("text/csv") and len(rows) >= 2
    j = list(csv.DictReader(io.StringIO(enterprise.export(pid, "journal")[0])))
    assert len(j) == 6 and sum(float(r["amount"]) for r in j) == 0
    x = list(csv.DictReader(io.StringIO(enterprise.export(pid, "xero")[0])))
    assert len(x) == 1 and x[0]["*UnitAmount"] == "10.00" and "TEST MONEY" in x[0]["Description"]
    with pytest.raises(ValueError):
        enterprise.export(pid, "sap")


@pytest.mark.skipif(not shutil.which("hledger"), reason="hledger is not installed")
def test_journal_imports_into_hledger(tmp_path):
    pid = _project_with_orders()
    (tmp_path / "knos.csv").write_text(enterprise.export(pid, "journal")[0], encoding="utf-8")
    (tmp_path / "knos.csv.rules").write_text(enterprise.HLEDGER_RULES, encoding="utf-8")
    out = subprocess.run(["hledger", "-f", str(tmp_path / "knos.csv"), "bal", "--flat", "-O", "csv"], capture_output=True, text=True, check=True)
    bal = {r[0]: r[1] for r in csv.reader(io.StringIO(out.stdout)) if len(r) == 2}
    assert bal["Expenses:Milestones paid"] == "USD10.00" and bal["Liabilities:Milestone commitments"] == "USD-12.00"


def test_dsse_roundtrip_and_tamper():
    st = {"_type": provenance.STATEMENT, "subject": [{"name": "result:https://a", "digest": {"sha256": "0" * 64}}],
          "predicateType": provenance.PREDICATE, "predicate": {"x": 1}}
    env = provenance.sign_envelope(st)
    key = provenance.public_key()
    ok = provenance.verify_envelope(env, key["public_key_hex"])
    assert ok["valid"] and ok["statement"] == st and ok["keyid"] == key["keyid"]
    bad = {**env, "payload": base64.b64encode(json.dumps({**st, "predicate": {"x": 2}}).encode()).decode()}
    assert provenance.verify_envelope(bad, key["public_key_hex"])["valid"] is False
    assert provenance.pae("a", b"bc") == b"DSSEv1 1 a 2 bc"


@pytest.mark.skipif(not provenance.c2pa_available(), reason="c2pa-python is not installed")
def test_c2pa_sign_and_read():
    import struct as s
    import zlib
    rows = b"".join(b"\x00" + b"\x10\x20\x30" * 8 for _ in range(8))
    c = lambda t, d: s.pack(">I", len(d)) + t + d + s.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    png = b"\x89PNG\r\n\x1a\n" + c(b"IHDR", s.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(rows)) + c(b"IEND", b"")
    out = provenance.c2pa_sign(png, "image/png", "knos-idea:abc123")
    m = out["manifest"]
    assert m["knos"]["claim_id"] == "knos-idea:abc123" and "TEST" in m["certificate"]
    assert provenance.c2pa_read(base64.b64decode(out["signed"]), "image/png")["knos"]["claim_id"] == "knos-idea:abc123"


def test_openapi_covers_every_route():
    doc = openapi.document("https://knos.example")
    assert openapi.validate(doc) == []
    paths = doc["paths"]
    for p in server.ROUTES:
        assert "post" in paths[p], p
    for m, p, *_ in product_routes.ROUTES:
        assert m.lower() in paths[p], p
    src = open(server.__file__, encoding="utf-8").read()
    body = src[src.index("def do_GET"):src.index("def status(")]
    for p in set(re.findall(r'u\.path == "([^"]+)"', body)) | {x for t in re.findall(r'u\.path in \(([^)]*)\)', body) for x in re.findall(r'"([^"]+)"', t)}:
        if p.endswith(".html") or p == "/index.html":
            continue
        assert p in paths, f"GET {p} is not in the OpenAPI document"
    assert paths["/api/project/claim"]["post"]["security"] == [{"session": []}]
    assert "/mcp" in paths and paths["/r/{code}"]["get"]["parameters"][0]["in"] == "path"
