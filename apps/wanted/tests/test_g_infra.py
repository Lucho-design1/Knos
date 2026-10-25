"""Self-hosted test IdP (Keycloak) through SAML Jackson, ERP imports (Odoo XML-RPC, ERPNext REST) with fakes, the kind
values for the Helm chart, and the recorded infrastructure proofs the Teams page shows."""
import json
import pathlib
import shutil
import subprocess
import urllib.parse

import pytest

from knos_wanted import enterprise, erp_import

ROOT = pathlib.Path(__file__).resolve().parents[3]
JOURNAL = """date,description,account,amount,reference,status
2026-10-17,"P: m1 (released, funder)",Expenses:Milestones paid,10.00,KNOS-77pBPLRi8PC,released
2026-10-17,"P: m1 (released, funder)",Assets:Knos money held,-10.00,KNOS-77pBPLRi8PC,released
2026-10-17,"P: m2 (locked, grant)",Assets:Knos money held,5.00,KNOS-4ZLF59p4KR3,locked
2026-10-17,"P: m2 (locked, grant)",Liabilities:Milestone commitments,-5.00,KNOS-4ZLF59p4KR3,locked
"""


class Resp:
    def __init__(self, raw=b"{}"):
        self.raw = raw

    def read(self, n=-1):
        return self.raw

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_keycloak_test_tenant_registered_in_jackson(monkeypatch):
    from knos_wanted import saml_sp
    monkeypatch.setattr(saml_sp, "available", lambda: False)      # the Jackson path (a test tenant goes to saml_sp when it can)
    monkeypatch.setenv("KNOS_SSO_URL", "https://jackson.test")
    monkeypatch.setenv("KNOS_SSO_CLIENT_SECRET", "v")
    monkeypatch.setenv("KNOS_SSO_API_KEY", "k")
    monkeypatch.setenv("KNOS_SSO_KEYCLOAK_URL", "https://idp.test/")
    enterprise._ensured.clear()
    seen = []

    def opener(req, timeout=60):
        seen.append((req.get_method(), req.full_url))
        u = urllib.parse.urlparse(req.full_url)
        if u.netloc == "idp.test":
            assert u.path == "/realms/knos-test"
            return Resp(b"{}")
        if u.path == "/api/v1/sso" and req.get_method() == "GET":
            return Resp(b"[]")
        if u.path == "/api/v1/sso":
            form = urllib.parse.parse_qs(req.data.decode())
            assert form["metadataUrl"] == ["https://idp.test/realms/knos-test/protocol/saml/descriptor"]
            assert form["tenant"] == ["knos-keycloak"] and "Keycloak" in form["name"][0]
            return Resp(b"{}")
        raise AssertionError(req.full_url)

    cfg = enterprise.sso_config()
    assert [t["tenant"] for t in cfg["test_tenants"]] == ["knos-test", "knos-keycloak"]
    url = enterprise.sso_start("knos-keycloak", "https://knos.example", opener=opener)
    assert url.startswith("https://jackson.test/api/oauth/authorize")
    assert urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["client_id"] == ["tenant=knos-keycloak&product=knos"]
    assert seen[0] == ("GET", "https://idp.test/realms/knos-test") and ("POST", "https://jackson.test/api/v1/sso") in seen


def test_keycloak_tenant_absent_without_url_and_refuses_plain_http(monkeypatch):
    monkeypatch.delenv("KNOS_SSO_KEYCLOAK_URL", raising=False)
    assert "knos-keycloak" not in enterprise.test_idps()
    monkeypatch.setenv("KNOS_SSO_KEYCLOAK_URL", "http://idp.example")
    assert "knos-keycloak" not in enterprise.test_idps()


def test_realm_file_has_no_secrets_and_matches_jackson():
    text = (ROOT / "deploy/sso/keycloak/knos-test-realm.json").read_text(encoding="utf-8")
    realm = json.loads(text)
    assert realm["realm"] == enterprise.KEYCLOAK_REALM and realm["registrationAllowed"] is False
    for u in realm["users"]:
        assert u["email"].endswith("@knos-test.example")
        assert all(c["value"].startswith("${KC_TEST_PASSWORD_") for c in u["credentials"])     # passwords come from env only
    key = realm["components"]["org.keycloak.keys.KeyProvider"][0]["config"]
    assert key["privateKey"] == ["${KC_REALM_PRIVATE_KEY}"]
    (client,) = realm["clients"]
    assert client["protocol"] == "saml" and "https://saml.knos.onrender.com" in client["clientId"]   # Jackson's SAML_AUDIENCE
    assert client["redirectUris"][0].endswith("/api/oauth/saml}")                                     # Jackson's ACS
    assert client["attributes"]["saml_name_id_format"] == "email"


def test_journal_entries_balance_and_reject_unknown():
    es = erp_import.entries(JOURNAL)
    assert [e["ref"] for e in es] == ["KNOS-77pBPLRi8PC released", "KNOS-4ZLF59p4KR3 locked"]
    assert erp_import.balances(es) == {"Assets:Knos money held": -5.0, "Expenses:Milestones paid": 10.0, "Liabilities:Milestone commitments": -5.0}
    with pytest.raises(erp_import.ImportError_):
        erp_import.entries(JOURNAL.replace("Assets:Knos money held", "Assets:Other"))
    with pytest.raises(erp_import.ImportError_):
        erp_import.entries(JOURNAL.replace("-5.00", "-4.00"))


class FakeOdoo:
    """Just enough of Odoo's ORM over XML-RPC: accounts, journals, moves and their lines."""
    def __init__(self):
        self.rows = {"account.journal": {1: {"type": "general"}}, "account.account": {}, "account.move": {}, "account.move.line": {}}
        self.n = 100

    def __call__(self, url, allow_none=True):
        return self

    def authenticate(self, db, user, pw, ctx):
        return 2 if pw == "pw" else False

    def execute_kw(self, db, uid, pw, model, method, args, kw):
        t = self.rows[model]
        if method == "search":
            return [i for i, r in t.items() if all(r.get(f) == v for f, _, v in args[0])][: kw.get("limit")]
        if method == "create":
            self.n += 1
            vals = dict(args[0])
            lines = vals.pop("line_ids", [])
            t[self.n] = vals
            for _, _, li in lines:
                lines_t = self.rows["account.move.line"]
                lines_t[len(lines_t) + 1] = {**li, "move": self.n}
            return self.n
        if method == "action_post":
            for i in args[0]:
                t[i]["state"] = "posted"
            return True
        if method == "search_read":
            ids = args[0][0][2]
            return [{"account_id": [li["account_id"], "x"], "debit": li["debit"], "credit": li["credit"],
                     "parent_state": self.rows["account.move"][li["move"]].get("state")}
                    for li in self.rows["account.move.line"].values() if li["move"] in ids]
        raise AssertionError(method)


def test_odoo_import_reads_back_the_same_balances():
    fake = FakeOdoo()
    r = erp_import.to_odoo(JOURNAL, "http://odoo", "knos", "admin", "pw", proxy=fake)
    assert r["match"] and r["posted"] and r["entries"] == 2 and len(fake.rows["account.account"]) == 4
    again = erp_import.to_odoo(JOURNAL, "http://odoo", "knos", "admin", "pw", proxy=fake)        # idempotent: no new moves
    assert again["moves"] == r["moves"] and len(fake.rows["account.move"]) == 2
    with pytest.raises(erp_import.ImportError_):
        erp_import.to_odoo(JOURNAL, "http://odoo", "knos", "admin", "wrong", proxy=fake)


class FakeFrappe(erp_import.Frappe):
    def __init__(self):
        self.docs = {"Company": [{"name": "Knos Test", "abbr": "KT"}], "Account": [], "Journal Entry": [], "GL Entry": []}

    def find(self, doctype, filters, fields=("name",)):
        def ok(d):
            for f, op, v in filters:
                if op == "=" and d.get(f) != v or op == "in" and d.get(f) not in v:
                    return False
            return True
        return [d for d in self.docs[doctype] if ok(d)]

    def make(self, doctype, doc):
        d = {**doc, "name": doc.get("account_name") or f"ACC-JV-{len(self.docs[doctype]) + 1}"}
        self.docs[doctype].append(d)
        if doctype == "Journal Entry":
            for a in doc["accounts"]:
                self.docs["GL Entry"].append({"voucher_no": d["name"], "is_cancelled": 0, "account": a["account"],
                                              "debit": a["debit_in_account_currency"], "credit": a["credit_in_account_currency"]})
        return d


def test_erpnext_import_reads_back_the_same_balances():
    f = FakeFrappe()
    r = erp_import.to_erpnext(JOURNAL, f, "Knos Test")
    assert r["match"] and r["gl_entries"] == 4 and len(r["journal_entries"]) == 2
    assert all(a["parent_account"].endswith(" - KT") for a in f.docs["Account"])
    with pytest.raises(erp_import.ImportError_):
        erp_import.to_erpnext(JOURNAL, f, "Nope")


@pytest.mark.skipif(not shutil.which("helm"), reason="helm is not installed")
def test_kind_values_render_a_local_image():
    out = subprocess.run(["helm", "template", "knos", str(ROOT / "deploy/selfhost/knos"), "-f", str(ROOT / "deploy/selfhost/kind-values.yaml")],
                         capture_output=True, text=True, check=True).stdout
    assert 'image: "knos:local"' in out and "imagePullPolicy: Never" in out and "/healthz" in out


def test_recorded_proofs_are_served_and_hold_no_secrets():
    from knos_wanted import product_routes, proofs
    rec = proofs.record()
    keys = [p["key"] for p in rec["proofs"]]
    assert {"selfhost_k8s", "sso_keycloak", "erp_odoo", "erp_erpnext", "erp_hledger", "sigstore"} <= set(keys)
    for p in rec["proofs"]:
        assert {"title", "where", "result", "summary", "run_yourself"} <= set(p) and p["result"] in ("pass", "not run")
    text = json.dumps(rec)
    for secret in ("KC_TEST_PASSWORD", "KC_REALM_PRIVATE_KEY", "BEGIN PRIVATE", "Api-Key ", "Bearer ey", "trycloudflare.com"):
        assert secret not in text
    paths = {r[1] for r in product_routes.ROUTES}
    assert set(proofs.FILES) <= paths                        # each served file is a documented route (OpenAPI)
    body, ctype = proofs.raw("/api/proofs")
    assert json.loads(body) == rec and ctype == "application/json"
    assert proofs.raw("/api/proofs/nothing") is None


@pytest.mark.skipif(not shutil.which("cosign"), reason="cosign is not installed")
def test_proofs_record_signature_verifies_with_cosign():
    d = ROOT / "apps/wanted/knos_wanted/data"
    subprocess.run(["cosign", "verify-blob", "--key", str(d / "proofs.cosign.pub"), "--bundle", str(d / "proofs.record.sigstore"),
                    "--insecure-ignore-tlog=true", str(d / "proofs.record")], check=True, capture_output=True)
