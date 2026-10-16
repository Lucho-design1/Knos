// Knos: researcher, buyer and maker views. No framework, no key: every Qloo call happens on the server.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const X = (sig, kind) => `https://explorer.solana.com/${kind || "tx"}/${sig}?cluster=devnet`;
const short = (s) => String(s || "").slice(0, 8) + "…";
let session = null, report = null, status = {};
try { session = JSON.parse(localStorage.getItem("knos.session") || "null"); } catch (e) { session = null; }

async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (session && session.token) headers.Authorization = "Bearer " + session.token;
  const r = await fetch(path, body === undefined ? { headers } : { method: "POST", headers, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.message || "HTTP " + r.status);
  return data;
}
let slowTimer = null;
function slow(on, what) {
  clearTimeout(slowTimer); const el = $("slow");
  if (!on) { el.hidden = true; return; }
  el.hidden = false; el.textContent = what + "…";
  slowTimer = setTimeout(() => { el.textContent = what + "… still working: a free server can take up to a minute to wake."; }, 6000);
}
function err(e) { const b = $("err"); b.hidden = !e; b.textContent = e ? String(e.message || e) : ""; if (e) b.scrollIntoView({ block: "nearest" }); }
async function busy(btn, text, fn) {
  const t = btn.textContent; btn.disabled = true; btn.textContent = text; slow(true, text); err(null);
  try { return await fn(); } catch (e) { err(e); } finally { btn.disabled = false; btn.textContent = t; slow(false); }
}

// ---- views ---------------------------------------------------------------------------------------------------------
function show() {
  const h = location.hash;
  const m = h.match(/^#buy=([0-9a-f]{64})/);
  const view = m ? "buy" : h.startsWith("#make") ? "make" : h.startsWith("#buy") ? "buy" : "research";
  for (const v of ["research", "buy", "make"]) $("v-" + v).hidden = v !== view;
  document.querySelectorAll(".views a").forEach((a) => a.classList.toggle("on", a.dataset.view === view));
  if (m) loadProduct(m[1]);
  if (view === "make") loadMaker();
}
window.addEventListener("hashchange", show);

// ---- sign in -------------------------------------------------------------------------------------------------------
function b64u(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function unb64u(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); const b = atob(s + "===".slice((s.length + 3) % 4)); return Uint8Array.from(b, (c) => c.charCodeAt(0)); }
function setSession(s) {
  session = s; try { s ? localStorage.setItem("knos.session", JSON.stringify(s)) : localStorage.removeItem("knos.session"); } catch (e) { /* private */ }
  $("whoBtn").textContent = s ? s.label : "Sign in"; $("outBtn").hidden = !s; if (s) $("signin").hidden = true;
}
async function passkeyNew() {
  const ch = await api("/api/auth/challenge", {}); const label = $("email").value.trim() || "Knos user";
  const cred = await navigator.credentials.create({ publicKey: { challenge: unb64u(ch.challenge), rp: { name: "Knos", id: ch.rp_id },
    user: { id: crypto.getRandomValues(new Uint8Array(16)), name: label, displayName: label }, pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    attestation: "none", timeout: 60000, authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" } } });
  setSession(await api("/api/auth/passkey/register", { id: cred.id, clientDataJSON: b64u(cred.response.clientDataJSON),
    publicKey: b64u(cred.response.getPublicKey()), alg: cred.response.getPublicKeyAlgorithm(), label }));
}
async function passkeyUse() {
  const ch = await api("/api/auth/challenge", {});
  const a = await navigator.credentials.get({ publicKey: { challenge: unb64u(ch.challenge), rpId: ch.rp_id, userVerification: "preferred", timeout: 60000 } });
  setSession(await api("/api/auth/passkey/login", { id: a.id, clientDataJSON: b64u(a.response.clientDataJSON),
    authenticatorData: b64u(a.response.authenticatorData), signature: b64u(a.response.signature) }));
}
function google(clientId) {
  $("googleBox").hidden = false;
  const s = document.createElement("script"); s.src = "https://accounts.google.com/gsi/client"; s.async = true;
  s.onload = () => { window.google.accounts.id.initialize({ client_id: clientId, callback: async (r) => { try { setSession(await api("/api/auth/google", { credential: r.credential })); } catch (e) { err(e); } } });
    window.google.accounts.id.renderButton($("gsi"), { theme: "outline", size: "large", width: 280 }); };
  document.head.appendChild(s);
}
async function emailGo() {
  if (status.auth && status.auth.email_provider) { const r = await api("/api/auth/email", { email: $("email").value }); $("emailNote").textContent = "A sign-in link was sent to " + r.to + "."; }
  else setSession(await api("/api/auth/guest", { label: $("email").value }));
}

// ---- researcher: the live crossing ---------------------------------------------------------------------------------
const KIND = { memory: "Memory", paper: "Paper", qloo: "Qloo", decision: "Decision" };
function stepHtml(s) {
  return `<li class="step ${esc(s.kind)}"><div class="row"><span class="tag">${KIND[s.kind] || s.kind}</span><b>${esc(s.title)}</b><span class="muted small">${esc(s.at)}</span></div>` +
    (s.tool ? `<p class="small mono">${esc(s.tool)}</p>` : "") + (s.output ? `<p>${esc(s.output)}</p>` : "") +
    (s.effect ? `<p class="small effect">→ ${esc(s.effect)}</p>` : "") +
    (s.input && typeof s.input === "object" ? `<details class="small"><summary>input</summary><pre>${esc(JSON.stringify(s.input, null, 1))}</pre></details>` : "") + "</li>";
}
async function cross() {
  const body = { ref: $("ref").value.trim() || undefined, idea: $("idea").value.trim() || undefined, product: $("product").value.trim() || undefined, place: $("place").value.trim() || undefined };
  const j = await api("/api/cross", body);
  $("timeline").hidden = false; $("steps").innerHTML = ""; $("outcome").innerHTML = ""; $("timeline").scrollIntoView({ behavior: "smooth" });
  let since = 0;
  for (let i = 0; i < 400; i++) {
    const p = await api(`/api/cross?id=${j.id}&since=${since}`);
    for (const s of p.steps) $("steps").insertAdjacentHTML("beforeend", stepHtml(s));
    since = p.total;
    if (p.status !== "running") {
      if (p.status === "error") throw new Error(p.error || "the crossing stopped");
      if (p.report) { const r = await api("/api/report?hash=" + p.report); report = r; outcome(r); }
      return;
    }
    await new Promise((res) => setTimeout(res, 900));
  }
}
function outcome(r) {
  const d = r.decision || {}, p = d.plan;
  $("outcome").innerHTML = `<div class="decision ${esc((d.verdict || "").toLowerCase())}"><h3>${esc(d.verdict)}</h3>` +
    (p ? `<p><b>Who:</b> ${esc((p.who.age || "").replace(/_/g, " "))}, ${esc(p.who.gender)}; ${esc((p.who.segments || []).join(", "))}</p>
      <p><b>Where:</b> ${esc((p.where || []).join(", ") || "n/a")}</p><p><b>Price:</b> ${esc(p.tier)} tier, ${p.unit_price} test units per unit</p>
      <p><b>Escrow:</b> target ${p.target_units} units (${p.escrow_target} test units), reserve ${p.reserve_units} (${p.escrow_reserve})</p>
      <p><a class="button" href="#buy=${r.hash}">Open the product page</a></p>` : `<ul>${(d.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`) + "</div>";
}

// ---- buyer ---------------------------------------------------------------------------------------------------------
async function loadProduct(h) {
  try {
    const r = await api("/api/report?hash=" + h); report = r;
    const d = r.decision || {}, p = d.plan || {}, rs = r.research;
    $("productCard").innerHTML = `<p class="label">${esc(r.label)}</p><h1>${esc(r.idea)}</h1>` +
      (rs ? `<p class="small">From the research: <a href="${esc(rs.proven_result.source || "#")}" target="_blank" rel="noopener">${esc(rs.title)}</a> (${esc(rs.year)}; cited ${esc(rs.cited_by_count)})</p>` : "") +
      (p.who ? `<div class="grid"><div><h3>For</h3><p>${esc((p.who.age || "").replace(/_/g, " "))}, ${esc(p.who.gender)}</p><p class="small muted">${esc((p.who.segments || []).join(", "))}</p></div>
        <div><h3>Launching in</h3><p>${esc((p.where || []).join(", "))}</p></div><div><h3>Price</h3><p>${p.unit_price} test units per unit (${esc(p.tier)})</p></div>
        <div><h3>Funding goal</h3><p>${p.target_units} units; the maker is paid on proof once ${p.reserve_units} are pre-ordered</p></div></div>` +
        (p.unserved_audience && p.unserved_audience.length ? `<p class="small">Who the leader does not serve: ${esc(p.unserved_audience.join(", "))}</p>` : "")
        : `<p>${esc(d.verdict)}: ${esc((d.reasons || []).join("; "))}</p>`);
    $("buyBox").hidden = d.verdict !== "OPEN";
    if (r.fees && r.fees.text) $("feeLine").textContent = r.fees.text + ".";
    const action = `${location.origin}/api/actions/preorder?report=${r.hash}`;
    $("blinkLink").href = "https://dial.to/?action=" + encodeURIComponent("solana-action:" + action) + "&cluster=devnet";
    $("tracker").hidden = false;
    $("trackList").innerHTML = (r.preorders || []).map((o) => `<li>${esc(o.units)} units, <b>${esc(o.status)}</b> · <a href="${X(o.order, "address")}" target="_blank" rel="noopener">escrow ${short(o.order)}</a></li>`).join("") || "<li class='muted'>No pre-orders yet.</li>";
    const res = r.reserve || {};
    if (res.reserve_units) $("trackList").insertAdjacentHTML("afterbegin", `<li>Reserve: ${res.pre_ordered_units} of ${res.reserve_units} units <progress max="${res.reserve_units}" value="${Math.min(res.pre_ordered_units, res.reserve_units)}"></progress></li>`);
  } catch (e) { err(e); }
}
function receipt(p) {
  const sigs = p.signatures || {};
  $("receipt").innerHTML = `<div class="decision open"><h3>Locked in escrow</h3><p>${esc(p.units)} units · <a href="${X(p.commitment, "address")}" target="_blank" rel="noopener">escrow order ${short(p.commitment)}</a></p>` +
    Object.entries(sigs).map(([k, s]) => `<p class="small">${esc(k.replace(/_/g, " "))}: <a href="${X(s)}" target="_blank" rel="noopener">${short(s)}</a></p>`).join("") +
    `<p class="small muted">Claim id for the maker's proof: ${esc(p.claim_id)}</p></div>`;
}
async function loadWeb3() {
  if (window.solanaWeb3) return window.solanaWeb3;
  await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "https://unpkg.com/@solana/web3.js@1.98.0/lib/index.iife.min.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  return window.solanaWeb3;
}
async function walletPreorder() {
  const w = window.phantom && window.phantom.solana || window.solflare || window.solana;
  if (!w) { window.open($("blinkLink").href, "_blank"); throw new Error("No wallet in this browser: the Blink opened in a new tab."); }
  const web3 = await loadWeb3(); await w.connect(); const account = w.publicKey.toString();
  const r = await fetch(`/api/actions/preorder?report=${report.hash}&units=${parseInt($("units").value, 10)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ account }) });
  const a = await r.json(); if (!r.ok) throw new Error(a.message || "the transaction could not be built");
  const tx = web3.Transaction.from(Uint8Array.from(atob(a.transaction), (c) => c.charCodeAt(0)));
  const signed = await w.signTransaction(tx);
  const sig = await new web3.Connection("https://api.devnet.solana.com", "confirmed").sendRawTransaction(signed.serialize());
  receipt({ units: $("units").value, commitment: a.commitment, signatures: { lock: sig }, claim_id: "shown once the order is on chain" });
  setTimeout(() => loadProduct(report.hash), 8000);
}

// ---- maker / funder ------------------------------------------------------------------------------------------------
async function loadMaker() {
  try {
    const { commitments } = await api("/api/commitments");
    $("makeList").innerHTML = commitments.map((c) => `<li class="card"><b>${esc((c.idea || "").slice(0, 80))}</b> · ${esc(c.units)} units × ${esc(c.unit_price)} · <b>${esc(c.status)}</b>
      <p class="small"><a href="${X(c.commitment, "address")}" target="_blank" rel="noopener">escrow ${short(c.commitment)}</a> · claim id <span class="mono">${esc(c.claim_id)}</span> · ${esc(c.via)}</p>
      ${Object.entries(c.signatures || {}).map(([k, s]) => `<span class="small">${esc(k.replace(/_/g, " "))}: <a href="${X(s)}" target="_blank" rel="noopener">${short(s)}</a></span>`).join(" · ")}
      ${c.status === "locked" ? `<div class="row gap"><input class="ev" data-c="${esc(c.commitment)}" type="url" placeholder="https://… evidence page"><button class="msBtn" data-c="${esc(c.commitment)}" type="button">Prove and release</button></div>
        <button class="fBtn ghost" data-c="${esc(c.commitment)}" type="button">Get cash now (factoring)</button>` : ""}
      ${c.factoring ? `<p class="small warn">Factoring: ${esc(c.factoring.status)}. ${esc(c.factoring.note)} Advance ${esc(c.factoring.advance)} on ${esc(c.factoring.face_value)} test units.</p>` : ""}</li>`).join("") || "<li class='muted'>No commitments yet.</li>";
    document.querySelectorAll(".msBtn").forEach((b) => b.onclick = () => busy(b, "Verifying", async () => {
      if (!session) { $("signin").hidden = false; throw new Error("Sign in first."); }
      const url = document.querySelector(`.ev[data-c="${b.dataset.c}"]`).value; await api("/api/milestone", { commitment: b.dataset.c, evidence_url: url }); loadMaker(); }));
    document.querySelectorAll(".fBtn").forEach((b) => b.onclick = () => busy(b, "Simulating the Assign on devnet", async () => {
      if (!session) { $("signin").hidden = false; throw new Error("Sign in first."); }
      await api("/api/factor", { commitment: b.dataset.c, discount_bps: 500 }); loadMaker(); }));
  } catch (e) { err(e); }
}

// ---- wiring --------------------------------------------------------------------------------------------------------
async function boot() {
  const h = location.hash;
  const m = h.match(/session=([^&]+)/);
  if (m) { try { const tok = decodeURIComponent(m[1]); const body = JSON.parse(atob((tok.split(".")[0] + "===").slice(0, Math.ceil(tok.split(".")[0].length / 4) * 4).replace(/-/g, "+").replace(/_/g, "/"))); setSession({ token: tok, ...body }); } catch (e) { /* bad link */ } history.replaceState(null, "", "#research"); }
  const mg = h.match(/magic=([^&]+)/);
  if (mg) { try { setSession(await api("/api/auth/email/verify", { token: decodeURIComponent(mg[1]) })); } catch (e) { err(e); } history.replaceState(null, "", "#research"); }
  setSession(session);
  try {
    status = await api("/api/status");
    const rest = status.qloo_rest || {};
    $("modeBadge").textContent = rest.rest ? "Qloo: live" : "Qloo: off"; $("modeBadge").className = "badge " + (rest.rest ? "live" : "off");
    const a = status.auth || {};
    if (a.google_client_id) google(a.google_client_id);
    $("orcidBtn").hidden = !a.orcid;
    if (!a.passkey || !window.PublicKeyCredential) { $("pkNew").disabled = $("pkUse").disabled = true; $("pkNote").textContent = "Passkeys are not available here."; }
    $("emailNote").textContent = (a.email_note || "") + ".";
    $("emailBtn").textContent = a.email_provider ? "Email me a sign-in link" : "Continue with this label";
  } catch (e) { err(e); }
  show();
}
$("whoBtn").onclick = () => { $("signin").hidden = !$("signin").hidden; };
$("outBtn").onclick = () => setSession(null);
$("pkNew").onclick = () => busy($("pkNew"), "Creating your passkey", passkeyNew);
$("pkUse").onclick = () => busy($("pkUse"), "Checking your passkey", passkeyUse);
$("emailBtn").onclick = () => busy($("emailBtn"), "Signing in", emailGo);
document.querySelectorAll(".chip").forEach((c) => c.onclick = () => { $("ref").value = c.dataset.ref; });
$("crossForm").onsubmit = (ev) => { ev.preventDefault(); busy($("crossBtn"), "The agent is crossing", cross); };
$("walletBtn").onclick = () => busy($("walletBtn"), "Waiting for your wallet", walletPreorder);
$("preBtn").onclick = () => busy($("preBtn"), "Locking on devnet", async () => {
  if (!session) { $("signin").hidden = false; throw new Error("Sign in first: passkey, email, Google or ORCID."); }
  const p = await api("/api/preorder", { report: report.hash, units: parseInt($("units").value, 10) }); receipt(p); loadProduct(report.hash); });
boot();
