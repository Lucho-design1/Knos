"""Evidence run: every role of Knos on a phone, against a base URL, with video and screenshots, end to end.

    python apps/wanted/e2e/roles.py https://knos.onrender.com --out evidence-run/ \
        [--evidence-dir DIR --evidence-url URL] [--topup-cmd CMD] [--note TEXT]
    (needs: pip install playwright; playwright install chromium)

Each role runs in its own browser context on a 375x812 phone viewport (touch, mobile) with a video recording, and a
virtual WebAuthn authenticator added over the Chrome DevTools Protocol (WebAuthn.addVirtualAuthenticator: ctap2,
internal, resident keys, user verification), so passkeys are really created and used by the app's own code: the
sign-in, and every payment (LazorKit smart wallet, secp256r1 precompile) through static/passkey_wallet.js.

One story, nothing stood in for:
  researcher   crosses a paper with a product idea (live Qloo on the server): the decision opens pre-orders
  maker        signs in with a passkey and claims the milestone (its receivable is paid to a wallet its passkey owns)
  buyer        gets devnet test units and pre-orders the reserve with its OWN passkey wallet (a PANEL order of knos_pay)
  funder       acts as the lender: quotes an advance on the receivable; the maker's passkey sells it (TransferOwnership);
               the lender's passkey pays the advance; after the release the lender's passkey collects
  maker        publishes its result page (with the claim id) and posts it: the referee panel (the FROST group key; 2 of
               3 hosts re-check the page and sign) releases the order to the receivable wallet the lender now owns
  contributor  submits work to the open knos.game round; a scored attempt's prize (funded by the round's sponsor) is
               released by the same FROST referee group
  agent        talks JSON-RPC to <base>/mcp
Writes <out>/<role>.png (+ <role>-<step>.png), <out>/<role>.webm and <out>/summary.json (PASS/FAIL per role, what was
seen, every devnet signature). Money: Solana devnet test units only.

--evidence-dir/--evidence-url: where the maker's result page is written and the public https URL it is served at.
--topup-cmd: a command run as `CMD <vault> <units>` when a passkey wallet needs more devnet test units than the
faucet's per-hour limit gives (the operator of the test mint tops it up; labelled in the summary).
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

PHONE = {"viewport": {"width": 375, "height": 812}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True,
         "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"}
DOI = "10.1038/nature16521"
PRODUCT = "a fitness watch with a sweat glucose sensor"
ROLES = ("researcher", "maker", "buyer", "funder", "contributor", "agent")
TRAIN = Path(__file__).resolve().parents[3] / "examples" / "autoresearch" / "train.py"
SIG = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{80,90}$")


class Run:
    def __init__(self, browser, base: str, out: Path, args):
        self.base, self.out, self.args = base, out, args
        self.summary = {"base": base, "viewport": "375x812 phone", "webauthn": "CDP WebAuthn.addVirtualAuthenticator (ctap2, internal)",
                        "note": args.note, "roles": {}, "signatures": {}, "topups": []}
        self.ctx, self.page, self.auth = {}, {}, {}
        for role in ROLES:
            vid = out / f"_video_{role}"
            c = browser.new_context(**PHONE, record_video_dir=str(vid), record_video_size={"width": 375, "height": 812},
                                    extra_http_headers=dict(h.split(":", 1) for h in args.header))
            p = c.new_page()
            cdp = c.new_cdp_session(p)
            cdp.send("WebAuthn.enable")
            got = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                                                                            "hasUserVerification": True, "isUserVerified": True,
                                                                            "automaticPresenceSimulation": True}})
            self.ctx[role], self.page[role], self.auth[role] = c, p, {"cdp": cdp, "id": got["authenticatorId"]}
            self.summary["roles"][role] = {"result": "PASS", "seen": [], "error": None, "screenshots": []}

    # -- helpers -------------------------------------------------------------------------------------------------
    def see(self, role, text):
        self.summary["roles"][role]["seen"].append(text)
        print(f"[{time.strftime('%H:%M:%S')}] {role}: {text[:220]}", flush=True)

    def shot(self, role, step):
        f = f"{role}-{step}.png"
        self.page[role].screenshot(path=str(self.out / f), full_page=True)
        self.summary["roles"][role]["screenshots"].append(f)

    def sigs(self, key, got):
        found = {k: v for k, v in _flat(got).items() if isinstance(v, str) and SIG.match(v)}
        if found:
            self.summary["signatures"][key] = found
        return found

    def api(self, role, path, body=None):
        """The app's own api() in the role's page (its session token)."""
        return self.page[role].evaluate("([p, b]) => api(p, b === null ? undefined : b)", [path, body])

    def creds(self, role) -> int:
        a = self.auth[role]
        return len(a["cdp"].send("WebAuthn.getCredentials", {"authenticatorId": a["id"]}).get("credentials", []))

    def sign_in(self, role, view):
        p = self.page[role]
        p.goto(self.base + "/#" + view, wait_until="domcontentloaded")
        p.wait_for_function("() => typeof api === 'function'", timeout=30_000)
        p.click("#whoBtn")
        p.fill("#email", f"Playwright {role}")
        p.click("#pkNew")
        p.wait_for_function("() => { try { return !!JSON.parse(localStorage.getItem('knos.session')||'null'); } catch (e) { return false; } }", timeout=60_000)
        p.wait_for_timeout(800)
        self.see(role, f"passkey created and used to sign in ({self.creds(role)} credential on the virtual authenticator)")

    def click_until(self, role, selector, done_js, what, timeout=240, retry_on=("too many requests", "again", "try again", "transaction failed", "blockhash", "could not finish this step", "answered http 5", "could not be read")):
        """Click, wait for done_js; on a rate limit (shared tunnel address) or a transient error, wait and click again."""
        p, end = self.page[role], time.time() + timeout
        while True:
            p.locator(selector).first.click()
            try:
                p.wait_for_function(done_js, timeout=90_000)
                return
            except Exception:  # noqa: BLE001
                text = p.inner_text("body")[-2000:].lower()
                if time.time() > end or not any(r in text for r in retry_on):
                    raise RuntimeError(f"{what}: no result ({_err_line(text)})") from None
                self.see(role, f"{what}: server said '{_err_line(text)}': waiting 60 s and trying again")
                p.wait_for_timeout(60_000)
                p.reload(wait_until="domcontentloaded")
                p.wait_for_function("() => typeof api === 'function'", timeout=30_000)
                p.wait_for_timeout(2500)

    def topup(self, role, vault, units):
        if not self.args.topup_cmd:
            return
        cmd = shlex.split(self.args.topup_cmd) + [vault, str(units)]
        got = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        line = (got.stdout.strip().splitlines() or [""])[-1]
        self.summary["topups"].append({"role": role, "vault": vault, "units": units, "result": line[:200],
                                       "label": "operator top-up of devnet test units (the test mint's authority), beyond the faucet's hourly limit"})
        self.see(role, f"operator top-up of {units} devnet test units to {vault[:8]}…: {line[:120]}")

    def fund(self, role, need):
        """Bring the role's passkey wallet to `need` test units: the operator's top-up when one is configured, else the
        app's own faucet (25 units a press, twice an hour per address), waiting out its limit up to --faucet-wait min."""
        w = self.api(role, "/api/wallet", {})
        if w["balance_units"] >= need:
            return w
        if self.args.topup_cmd:
            self.topup(role, w["vault"], int(need - w["balance_units"]) + 1)
            return self.api(role, "/api/wallet", {})
        end = time.time() + 60 * self.args.faucet_wait
        while w["balance_units"] < need:
            try:
                got = self.api(role, "/api/wallet/faucet", {})
                self.sigs(f"{role} faucet {time.strftime('%H:%M:%S')}", {"faucet": got.get("signature")})
                self.see(role, f"faucet: +{got.get('units')} devnet test units ({str(got.get('signature'))[:16]}…)")
            except Exception as why:  # noqa: BLE001 - the faucet's hourly limit: wait for the window to move
                if time.time() > end or "too many" not in str(why).lower():
                    raise RuntimeError(f"the faucet: {why}") from None
                self.see(role, f"faucet limit reached ({str(why)[:80]}): waiting 5 minutes")
                self.page[role].wait_for_timeout(300_000)
                continue
            self.page[role].wait_for_timeout(3000)
            w = self.api(role, "/api/wallet", {})
        return w

    def hook(self, name):
        cmd = getattr(self.args, name)
        if cmd:
            got = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            self.summary.setdefault("hooks", []).append({"hook": name, "cmd": cmd, "exit": got.returncode, "out": got.stdout[-300:]})
            print(f"hook {name}: exit {got.returncode} {got.stdout[-200:]}", flush=True)

    def commitment(self, role, order):
        return self.api(role, "/api/commitment?id=" + order)

    def wait_status(self, role, order, want, timeout=600):
        end = time.time() + timeout
        while time.time() < end:
            c = self.commitment(role, order)
            st = (c.get("factoring") or {}).get("status") if want in ("assigned", "advanced", "repaid") else c.get("status")
            if st == want:
                return c
            self.page[role].wait_for_timeout(5000)
        raise RuntimeError(f"commitment {order[:8]}: not {want} after {timeout} s")

    def finish(self):
        for role in ROLES:
            try:
                self.page[role].screenshot(path=str(self.out / f"{role}.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
            vid = self.out / f"_video_{role}"
            self.ctx[role].close()
            v = next(vid.glob("*.webm"), None)
            if v:
                shutil.move(str(v), self.out / f"{role}.webm")
            shutil.rmtree(vid, ignore_errors=True)
            r = self.summary["roles"][role]
            r["screenshot"], r["video"] = f"{role}.png", f"{role}.webm"


def _flat(d, pre=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{pre}{k}.") if isinstance(v, (dict, list)) else {f"{pre}{k}": v})
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flat(v, f"{pre}{i}.") if isinstance(v, (dict, list)) else {f"{pre}{i}": v})
    return out


def _err_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return (lines[-1] if lines else "")[:160]


# -- the story ----------------------------------------------------------------------------------------------------------
def researcher(r: Run, st: dict):
    p = r.page["researcher"]
    if r.args.front_door:
        taps = 0
        p.goto(r.args.front_door, wait_until="domcontentloaded")
        p.wait_for_timeout(2500)
        r.shot("researcher", "front-door")
        nav = p.get_by_role("link", name=re.compile("Research products", re.I)).first
        typed = None
        if not nav.is_visible():                          # on a phone the views sit behind the Menu / More buttons
            for name in (r"^\s*Menu\s*$", r"^\s*More\s*$"):
                b = p.get_by_role("button", name=re.compile(name, re.I)).first
                if not nav.is_visible() and b.count() and b.is_visible():
                    b.click()
                    taps += 1
                    p.wait_for_timeout(800)
        if nav.count() and nav.is_visible():
            nav.click()
            taps += 1
        else:                                             # no link to the app on this front door: say so, type it
            typed = r.args.front_door.rstrip("/") + "/#apps"
            r.see("researcher", f"the front door shows no link to the app after {taps} taps; typed {typed}")
            p.goto(typed, wait_until="domcontentloaded")
        st["front_door_typed"] = typed
        p.wait_for_selector("#apps-go", timeout=30_000)
        p.click("#apps-go")
        taps += 1
        p.wait_for_url(re.compile(re.escape(r.base) + "|wanted\\.html"), timeout=120_000)
        if "wanted.html" in p.url:                         # the wake page forwards once the app answers
            p.wait_for_url(re.compile(re.escape(r.base)), timeout=180_000)
        st["front_door_taps"] = taps
        r.see("researcher", f"front door {r.args.front_door} -> {p.url} in {taps} taps")
        p.wait_for_function("() => typeof api === 'function'", timeout=60_000)
        p.evaluate("location.hash = '#research'")
        p.wait_for_timeout(1500)
    else:
        p.goto(r.base + "/#research", wait_until="domcontentloaded")
    p.fill("#ref", r.args.doi)
    p.fill("#product", r.args.product)
    if r.args.place:
        p.fill("#place", r.args.place)
    p.click("#crossBtn")
    p.wait_for_selector("#outcome .decision", timeout=600_000)
    rep = p.evaluate("report")
    d = rep.get("decision") or {}
    st["report"], st["reserve"] = rep["hash"], int(d.get("reserve_units") or 5)
    st["price"] = int((d.get("plan") or {}).get("unit_price") or 2)
    r.see("researcher", f"crossing decided {d.get('verdict')} ({rep.get('label', '')[:40]}): target {d.get('target_units')}, "
                        f"reserve {d.get('reserve_units')}, report {rep['hash'][:16]}")
    r.shot("researcher", "decision")
    if d.get("verdict") != "OPEN":
        raise RuntimeError("the decision is not OPEN: pre-orders stay closed")


def maker_claims(r: Run, st: dict):
    r.sign_in("maker", "buy=" + st["report"])
    p = r.page["maker"]
    p.goto(r.base + "/#buy=" + st["report"], wait_until="domcontentloaded")
    p.wait_for_selector("#buyBox:not([hidden])", timeout=60_000)
    r.click_until("maker", "#claimBtn", "() => document.querySelector('#claimNote').textContent.trim().length > 0", "claim")
    r.see("maker", "claimed the milestone: " + p.inner_text("#claimNote")[:140])
    r.shot("maker", "claimed")


def buyer(r: Run, st: dict):
    r.sign_in("buyer", "buy=" + st["report"])
    p = r.page["buyer"]
    p.goto(r.base + "/#buy=" + st["report"], wait_until="domcontentloaded")
    for _ in range(6):                                  # the page loads the wallet once; a failed read (devnet, DNS) hides it
        try:
            p.wait_for_selector("#pkWallet:not([hidden])", timeout=20_000)
            break
        except Exception:  # noqa: BLE001
            p.evaluate("loadWallet()")
    p.wait_for_selector("#pkWallet:not([hidden])", timeout=30_000)
    before = p.inner_text("#pkUnits")
    r.click_until("buyer", "#faucetBtn", f"() => document.querySelector('#pkUnits').textContent !== {json.dumps(before)}", "faucet")
    w = r.api("buyer", "/api/wallet", {})
    r.see("buyer", f"passkey wallet {w['vault']} holds {w['balance_units']} test units after the faucet")
    need = st["reserve"] * st.get("price", 2) + 2                  # the order (reserve x unit price) and its fee
    if w["balance_units"] < need:
        w = r.fund("buyer", need)
        p.evaluate("loadWallet()")
        p.wait_for_timeout(3000)
    r.see("buyer", f"passkey wallet holds {w['balance_units']} test units (needs {need})")
    p.fill("#units", str(st["reserve"]))
    r.click_until("buyer", "#preBtn", "() => /escrow|✓|[1-9A-HJ-NP-Za-km-z]{8}…/.test(document.querySelector('#receipt').innerText)", "pre-order", timeout=400)
    r.see("buyer", "pre-order signed by the buyer's passkey: " + p.inner_text("#receipt")[:200].replace("\n", " "))
    rows = [c for c in r.api("buyer", "/api/commitments")["commitments"] if c.get("report") == st["report"] and c.get("via_kind") == "preorder"]
    c = rows[0]
    st["order"], st["claim"] = c["commitment"], c["claim_id"]
    r.sigs("buyer pre-order", c.get("signatures"))
    r.see("buyer", f"order {c['commitment']} locked, {c['units']} units, claim {c['claim_id']}")
    r.shot("buyer", "preordered")


def lender_quotes(r: Run, st: dict):
    r.sign_in("funder", "fund")
    p = r.page["funder"]
    p.goto(r.base + "/#fund", wait_until="domcontentloaded")
    p.wait_for_function("() => typeof api === 'function'", timeout=30_000)
    face = st["reserve"] * st.get("price", 2)
    w = r.fund("funder", face * r.args.advance_rate / 100 + 0.5)
    r.see("funder", f"lender's passkey wallet {w['vault']}")
    p.reload(wait_until="domcontentloaded")
    sel = f".lendGo[data-go='quote'][data-c='{st['order']}']"
    p.wait_for_selector(sel, timeout=60_000)
    rate = str(r.args.advance_rate)
    p.locator(sel).locator("xpath=..").locator(".ar").fill(rate)
    r.click_until("funder", sel, f"() => !document.querySelector(\"{sel}\") || document.querySelector('#lendTable').innerText.includes('{rate}%')", "quote")
    r.see("funder", f"quoted a {rate}% advance on the receivable")
    r.shot("funder", "quoted")


def maker_sells(r: Run, st: dict):
    p = r.page["maker"]
    p.goto(r.base + "/#make", wait_until="domcontentloaded")
    sel = f".acBtn[data-c='{st['order']}']"
    p.wait_for_selector(sel, timeout=90_000)
    r.click_until("maker", sel, "() => /✓|[1-9A-HJ-NP-Za-km-z]{8}…/.test(document.querySelector('#receipt') ? document.querySelector('#receipt').innerText : '')", "sell the receivable", timeout=400)
    c = r.wait_status("maker", st["order"], "assigned", 180)
    r.sigs("maker sells the receivable (TransferOwnership)", c.get("factoring"))
    r.see("maker", "sold the receivable with its passkey (LazorKit TransferOwnership): " + json.dumps(c.get("factoring"))[:200])
    r.shot("maker", "sold")


def lender_advances(r: Run, st: dict):
    p = r.page["funder"]
    p.goto(r.base + "/#fund", wait_until="domcontentloaded")
    p.reload(wait_until="domcontentloaded")
    sel = f".lendGo[data-go='advance'][data-c='{st['order']}']"
    p.wait_for_selector(sel, timeout=90_000)
    r.click_until("funder", sel, f"() => !document.querySelector(\"{sel}\")", "advance", timeout=400)
    c = r.wait_status("funder", st["order"], "advanced", 180)
    r.sigs("lender pays the advance", c.get("factoring"))
    r.see("funder", "paid the advance with its passkey: " + json.dumps(c.get("factoring"))[:200])
    r.shot("funder", "advanced")


def maker_proves(r: Run, st: dict):
    p = r.page["maker"]
    if r.args.evidence_dir:
        page = (f"<!doctype html><meta charset=utf-8><title>Milestone result</title><h1>Milestone result</h1>"
                f"<p>Claim {st['claim']}: the prototype ({r.args.product}) was built and measured; result attached.</p>")
        Path(r.args.evidence_dir, "index.html").write_text(page, encoding="utf-8")
    url = r.args.evidence_url or ""
    if r.args.evidence_url_template:
        url = r.args.evidence_url_template.format(claim=st["claim"])
    elif url.startswith("@"):                              # a file holding the URL, read when the page is posted
        url = Path(url[1:]).read_text(encoding="utf-8").strip()
    if not r.args.evidence_url_template:
        url = url.rstrip("/") + "/"
    r.hook("hook_before_post")
    p.goto(r.base + "/#make", wait_until="domcontentloaded")
    sel = f".ev[data-c='{st['order']}']"
    p.wait_for_selector(sel, timeout=60_000)
    p.fill(sel, url)
    p.locator(f".msBtn[data-c='{st['order']}']").click()      # the server checks the page, then the referee group signs
    p.wait_for_timeout(8000)
    if "not verified" in p.inner_text("body").lower():
        raise RuntimeError("milestone not verified: " + _err_line(p.inner_text("body")))
    r.see("maker", f"posted the result page {url}: the FROST referee group checks it")
    r.shot("maker", "posted")
    c = r.wait_status("maker", st["order"], "released", 60 * r.args.release_wait)
    r.hook("hook_after_release")
    r.sigs("release by the FROST referee group", c.get("signatures"))
    sess = (c.get("referee_session") or {})
    r.see("maker", f"released by the FROST group key: signers {sess.get('signers')}, signature {str(sess.get('signature'))[:16]}…, "
                   f"release tx {(c.get('signatures') or {}).get('referee_group_pass')}")
    p.reload(wait_until="domcontentloaded")
    p.wait_for_timeout(2500)
    r.shot("maker", "released")


def lender_collects(r: Run, st: dict):
    p = r.page["funder"]
    p.goto(r.base + "/#fund", wait_until="domcontentloaded")
    p.reload(wait_until="domcontentloaded")
    sel = f".lendGo[data-go='collect'][data-c='{st['order']}']"
    p.wait_for_selector(sel, timeout=90_000)
    r.click_until("funder", sel, f"() => !document.querySelector(\"{sel}\")", "collect", timeout=400)
    c = r.wait_status("funder", st["order"], "repaid", 180)
    r.sigs("lender collects", c.get("factoring"))
    r.see("funder", "collected the repayment with its passkey: " + json.dumps(c.get("factoring"))[:200])
    r.shot("funder", "collected")


def contributor(r: Run, st: dict):
    r.sign_in("contributor", "contribute")
    p = r.page["contributor"]
    w = r.api("contributor", "/api/wallet", {})
    p.goto(r.base + "/#contribute", wait_until="domcontentloaded")
    p.wait_for_selector(".tBtn", timeout=60_000)
    p.locator(".tname").first.fill(f"pw{time.strftime('%H%M%S')}")
    p.locator(".twal").first.fill(w["vault"])
    # a real attempt: standardized inputs and squared features (the baseline itself is refused as "no change")
    code = TRAIN.read_text(encoding="utf-8").replace("'standardize': False", "'standardize': True").replace("'features': 'linear'", "'features': 'square'")
    p.locator(".tsub").first.fill(code)
    p.locator(".tBtn").first.click()
    p.wait_for_selector(".card .note", timeout=600_000)
    note = p.inner_text(".card .note")
    r.see("contributor", "the sealed referee answered: " + note[:220].replace("\n", " "))
    r.shot("contributor", "judged")
    m = re.search(r"session ([0-9a-f]{8})", note)
    if "scored" not in note:
        raise RuntimeError("the attempt was not scored")
    if not m:
        raise RuntimeError("no prize session: " + note[:200])
    sid = next(s["id"] for s in r.api("contributor", "/api/referee/pending")["sessions"] if s["id"].startswith(m.group(1)))
    end = time.time() + 900
    while time.time() < end:
        s = r.api("contributor", "/api/referee/session?id=" + sid)
        if s.get("state") == "signed" and s.get("result"):
            break
        p.wait_for_timeout(5000)
    r.sigs("prize release by the FROST referee group", s.get("result"))
    r.see("contributor", f"prize released by the FROST group (signers {s.get('signers')}): {json.dumps(s.get('result'))[:200]}")
    p.goto(f"https://explorer.solana.com/address/{w['vault']}?cluster=devnet", wait_until="domcontentloaded")
    p.wait_for_timeout(6000)
    r.shot("contributor", "paid")


def agent(r: Run, st: dict):
    p, out = r.page["agent"], []
    calls = [("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "playwright", "version": "1"}}),
             ("tools/list", {}), ("tools/call", {"name": "knos_milestones", "arguments": {}}), ("tools/call", {"name": "knos_templates", "arguments": {}})]
    for i, (method, params) in enumerate(calls, 1):
        q = p.request.post(r.base + "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}),
                           headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}, timeout=120_000)
        res = (q.json().get("result") or {})
        if method == "initialize":
            out.append(f"initialize {q.status}: {res.get('serverInfo')}")
        elif method == "tools/list":
            out.append(f"tools/list {q.status}: {len(res.get('tools', []))} tools")
        else:
            sc = res.get("structuredContent") or {}
            out.append(f"{params['name']} {q.status}: " + json.dumps(sc)[:220])
    for x in out:
        r.see("agent", x)
    html = "<meta name=viewport content='width=device-width'><body style='font:14px system-ui;padding:16px'><h1>Agent via MCP</h1>" + \
           f"<p>{r.base}/mcp</p>" + "".join(f"<p>{x.replace('<', '&lt;')}</p>" for x in out) + "</body>"
    p.set_content(html)
    p.wait_for_timeout(1200)
    r.shot("agent", "mcp")


STORY = [("researcher", researcher), ("maker", maker_claims), ("buyer", buyer), ("funder", lender_quotes), ("maker", maker_sells),
         ("funder", lender_advances), ("maker", maker_proves), ("funder", lender_collects), ("contributor", contributor), ("agent", agent)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--out", default="evidence-run")
    ap.add_argument("--doi", default=DOI)
    ap.add_argument("--product", default=PRODUCT)
    ap.add_argument("--place", default=None)
    ap.add_argument("--evidence-dir", default=None, help="the folder the maker's result page is written to")
    ap.add_argument("--evidence-url", default=None, help="the public https URL that folder is served at")
    ap.add_argument("--topup-cmd", default=None)
    ap.add_argument("--faucet-wait", type=int, default=0, help="minutes to wait out the faucet's hourly limit (live runs)")
    ap.add_argument("--advance-rate", type=int, default=90, help="the lender's advance rate, 50 to 98 percent")
    ap.add_argument("--front-door", default=None, help="start the researcher here and count the taps to the app")
    ap.add_argument("--evidence-url-template", default=None, help="the maker's public page, {claim} = the claim id")
    ap.add_argument("--hook-before-post", default=None, help="a shell command run before the maker posts its evidence")
    ap.add_argument("--hook-after-release", default=None, help="a shell command run after the release")
    ap.add_argument("--release-wait", type=int, default=15, help="minutes to wait for the referee group's release")
    ap.add_argument("--note", default="")
    ap.add_argument("--header", action="append", default=[], help="NAME:VALUE sent with every request (e.g. a tunnel's documented no-interstitial header)")
    ap.add_argument("--chromium", default=None, help="a Chrome/Chromium executable (default: Playwright's)")
    args = ap.parse_args(argv)
    if not (args.evidence_url or args.evidence_url_template):
        ap.error("--evidence-url or --evidence-url-template: the maker's result page must be a public https page")
    from playwright.sync_api import sync_playwright
    base, out = args.base.rstrip("/"), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    st: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.chromium) if args.chromium else pw.chromium.launch()
        r = Run(browser, base, out, args)
        t0 = time.time()
        for role, step in STORY:
            if any(v["result"] == "FAIL" for v in r.summary["roles"].values()) and role != "agent" and step is not contributor:
                r.summary["roles"][role]["seen"].append(f"skipped {step.__name__}: an earlier step failed")
                if r.summary["roles"][role]["result"] == "PASS":
                    r.summary["roles"][role].update(result="FAIL", error=f"not run: {step.__name__} needs an earlier step that failed")
                continue
            try:
                step(r, st)
            except Exception as why:  # noqa: BLE001 - a failed step is evidence too
                r.summary["roles"][role].update(result="FAIL", error=f"{step.__name__}: {type(why).__name__}: {str(why)[:300]}")
                print(role, "FAIL", r.summary["roles"][role]["error"], flush=True)
                try:
                    r.shot(role, "fail-" + step.__name__)
                except Exception:  # noqa: BLE001
                    pass
        r.summary["state"], r.summary["seconds"] = st, round(time.time() - t0, 1)
        r.finish()
        browser.close()
    (out / "summary.json").write_text(json.dumps(r.summary, indent=1), encoding="utf-8")
    for role, v in r.summary["roles"].items():
        print(role, v["result"], v["error"] or "", flush=True)
    return 0 if all(v["result"] == "PASS" for v in r.summary["roles"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
