"""SAML sign-in through SAML Jackson against a Keycloak test realm, with no browser (selfhost-proof.yml).

Usage: python ci_sso_saml.py <jackson url> <keycloak SAML descriptor url>. The test user's password is $ALICE and
Jackson's API key is $JACKSON_API (both made for this run only). Exits non-zero unless userinfo names the test user.
"""
import html
import os
import re
import sys
import urllib.parse

import requests

JK, DESC = sys.argv[1].rstrip("/"), sys.argv[2]
CB = "http://localhost:9999/cb"
s = requests.Session()
meta = s.get(DESC, timeout=30).text
r = s.post(f"{JK}/api/v1/sso", headers={"Authorization": f"Api-Key {os.environ['JACKSON_API']}"}, timeout=30,
           data={"rawMetadata": meta, "tenant": "knos-keycloak", "product": "knos", "defaultRedirectUrl": CB, "redirectUrl": f'["{CB}"]',
                 "name": "Keycloak test realm"})
r.raise_for_status()
q = {"response_type": "code", "client_id": "dummy", "tenant": "knos-keycloak", "product": "knos", "redirect_uri": CB, "state": "ci"}
page = s.get(f"{JK}/api/oauth/authorize?{urllib.parse.urlencode(q)}", timeout=60)
form = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', page.text)
assert form, f"no Keycloak login form at {page.url.split('?')[0]}"
done = s.post(html.unescape(form.group(1)), data={"username": "alice", "password": os.environ["ALICE"], "credentialId": ""}, timeout=60)
saml = re.search(r'name="SAMLResponse" value="([^"]+)"', done.text)
relay = re.search(r'name="RelayState" value="([^"]*)"', done.text)
acs = re.search(r'<form[^>]*action="([^"]+)"', done.text)
assert saml and acs, "Keycloak did not answer with a SAML response"
back = s.post(html.unescape(acs.group(1)), data={"SAMLResponse": saml.group(1), "RelayState": html.unescape(relay.group(1)) if relay else ""},
              allow_redirects=False, timeout=60)
loc = back.headers.get("Location", "")
code = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("code", [""])[0]
assert code, f"Jackson did not redirect with a code (HTTP {back.status_code})"
tok = s.post(f"{JK}/api/oauth/token", timeout=30, data={"grant_type": "authorization_code", "code": code, "redirect_uri": CB,
                                                       "client_id": "tenant=knos-keycloak&product=knos", "client_secret": "dummy"}).json()
me = s.get(f"{JK}/api/oauth/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=30).json()
print("signed in through SAML Jackson as", me.get("email"), "| id", str(me.get("id"))[:12])
assert me.get("email") == "alice@knos-test.example", me
