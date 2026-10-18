// Knos: six roles on one phone page. No framework; every taste call happens on the server.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const X = (sig, kind) => `https://explorer.solana.com/${kind || "tx"}/${sig}?cluster=devnet`;
const short = (s) => String(s || "").slice(0, 8) + "…";
let session = null, report = null, status = {};
try { session = JSON.parse(localStorage.getItem("knos.session") || "null"); } catch (e) { session = null; }

// ---- i18n ----------------------------------------------------------------------------------------------------------
const I = window.KNOS_I18N || { langs: { en: "English" }, rtl: [], en: {} };
let LANG = "en";
try { LANG = localStorage.getItem("knos.lang") || (navigator.language || "en").slice(0, 2); } catch (e) { /* private */ }
if (!I.langs[LANG]) LANG = "en";
const t = (k) => (I[LANG] && I[LANG][k]) || I.en[k] || k;
function applyLang() {
  document.documentElement.lang = LANG;
  document.documentElement.dir = I.rtl.includes(LANG) ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  if (session) $("whoBtn").textContent = session.label;
}
function langMenu() {
  // Only the current language is listed until the menu is used: the other names (Arabic, Hindi, Chinese scripts) make
  // the browser load fallback fonts, which cost seconds of style and layout on a phone's first paint (Lighthouse).
  const fill = (all) => { $("lang").innerHTML = Object.entries(I.langs).filter(([k]) => all || k === LANG).map(([k, v]) => `<option value="${k}" ${k === LANG ? "selected" : ""}>${esc(v)}</option>`).join(""); };
  fill(false);
  const more = () => { if (!$("lang").dataset.full) { $("lang").dataset.full = "1"; fill(true); } };
  for (const ev of ["focus", "pointerdown", "touchstart", "keydown"]) $("lang").addEventListener(ev, more, { passive: true });
  $("lang").onchange = () => { LANG = $("lang").value; try { localStorage.setItem("knos.lang", LANG); } catch (e) { } applyLang(); show(); };
}

// ---- plumbing ------------------------------------------------------------------------------------------------------
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
  el.hidden = false; $("slowText").textContent = what + "…";
  slowTimer = setTimeout(() => { $("slowText").textContent = what + "… (" + t("loading") + ")"; }, 6000);
}
function err(e) { const b = $("err"); b.hidden = !e; b.textContent = e ? String(e.message || e) : ""; if (e) b.scrollIntoView({ block: "nearest" }); }
async function busy(btn, text, fn) {
  const was = btn.textContent; btn.disabled = true; btn.textContent = text; slow(true, text); err(null);
  try { return await fn(); } catch (e) { err(e); } finally { btn.disabled = false; btn.textContent = was; slow(false); }
}

// ---- views ---------------------------------------------------------------------------------------------------------
const VIEWS = ["research", "buy", "fund", "contribute", "make", "projects", "teams", "agents"];
function show() {
  err(null); slow(false, "");
  const h = location.hash;
  const m = h.match(/^#buy=([0-9a-f]{64})/);
  let view = m ? "buy" : (h.slice(1).split("=")[0] || "research");
  if (!VIEWS.includes(view)) view = "research";
  for (const v of VIEWS) $("v-" + v).hidden = v !== view;
  document.documentElement.dataset.view = view;
  document.querySelectorAll("nav.roles a").forEach((a) => {
    a.classList.toggle("on", a.dataset.view === view);
    a.setAttribute("aria-current", a.dataset.view === view ? "page" : "false");
  });
  if (m) loadProduct(m[1]); else if (view === "buy") loadCrossings($("productCard"), true);
  if (view === "research") loadOpen();
  if (view === "make") loadMaker();
  if (view === "fund") loadFund();
  if (view === "contribute") loadTasks();
  if (view === "agents") loadAgents();
  if (window.KNOS_VIEW) window.KNOS_VIEW(view);       // projects + teams (valley.js)
}
window.addEventListener("hashchange", show);

// ---- sign in -------------------------------------------------------------------------------------------------------
function b64u(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function unb64u(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); const b = atob(s + "===".slice((s.length + 3) % 4)); return Uint8Array.from(b, (c) => c.charCodeAt(0)); }
function setSession(s) {
  session = s; try { s ? localStorage.setItem("knos.session", JSON.stringify(s)) : localStorage.removeItem("knos.session"); } catch (e) { /* private */ }
  $("whoBtn").textContent = s ? s.label : t("sign_in"); $("outBtn").hidden = !s; if (s) $("signin").hidden = true;
}
async function passkeyNew() {
  const ch = await api("/api/auth/challenge", {}); const label = $("email").value.trim() || "Knos user";
  const cred = await navigator.credentials.create({ publicKey: { challenge: unb64u(ch.challenge), rp: { name: "Knos", id: ch.rp_id },
    user: { id: crypto.getRandomValues(new Uint8Array(16)), name: label, displayName: label }, pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    attestation: "none", timeout: 60000, authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" } } });
  setSession(await api("/api/auth/passkey/register", { id: cred.id, clientDataJSON: b64u(cred.response.clientDataJSON),
    publicKey: b64u(cred.response.getPublicKey()), alg: cred.response.getPublicKeyAlgorithm(), label,
    authenticatorData: b64u(cred.response.getAuthenticatorData()) }));
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
  if (status.auth && status.auth.email_provider) { const r = await api("/api/auth/email", { email: $("email").value }); $("emailNote").textContent = "→ " + r.to; }
  else setSession(await api("/api/auth/guest", { label: $("email").value }));
}

// ---- researcher ----------------------------------------------------------------------------------------------------
const KIND = { memory: "Memory", paper: "Paper", qloo: "Qloo", decision: "Decision" };
function stepHtml(s) {
  return `<li class="step ${esc(s.kind)}"><div class="row"><span class="tag">${KIND[s.kind] || s.kind}</span><b>${esc(s.title)}</b><span class="muted small">${esc(s.at)}</span></div>` +
    (s.tool ? `<p class="small mono muted">${esc(s.tool)}</p>` : "") + (s.output ? `<p>${esc(s.output)}</p>` : "") +
    (s.effect ? `<p class="effect">→ ${esc(s.effect)}</p>` : "") +
    (s.input && typeof s.input === "object" ? `<details class="small"><summary>input</summary><pre>${esc(JSON.stringify(s.input, null, 1))}</pre></details>` : "") + "</li>";
}
async function loadOpen() {
  try {
    const { crossings } = await api("/api/crossings");
    const open = crossings.filter((c) => c.verdict === "OPEN").slice(0, 6);
    $("openNow").hidden = !open.length;
    $("openList").innerHTML = open.map((c) => `<li><a class="p" href="#buy=${esc(c.report)}"><span class="v">${esc(t("open_v"))}</span><br><b>${esc((c.idea || "").slice(0, 90))}</b><br><span class="small muted">${t("target")} ${c.target_units} · ${t("reserve")} ${c.reserve_units}</span></a></li>`).join("");
  } catch (e) { $("openNow").hidden = true; }
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
      if (p.status === "error") throw new Error(p.error || "stopped");
      if (p.report) { const r = await api("/api/report?hash=" + p.report); report = r; outcome(r); }
      return;
    }
    await new Promise((res) => setTimeout(res, 900));
  }
}
function outcome(r) {
  const d = r.decision || {}, p = d.plan;
  const word = d.verdict === "OPEN" ? t("open_v") : d.verdict === "REFUSE" ? t("refuse") : t("cannot");
  $("outcome").innerHTML = `<div class="decision ${esc((d.verdict || "").toLowerCase())}"><h3>${esc(word)}</h3>` +
    (p ? `<p><b>${t("for_l")}:</b> ${esc((p.who.age || "").replace(/_/g, " "))}, ${esc(p.who.gender)} · ${esc((p.who.segments || []).slice(0, 3).join(", "))}</p>
      <p><b>${t("where_l")}:</b> ${esc((p.where || []).join(", ") || "—")}</p><p><b>${t("price_l")}:</b> ${p.unit_price} ${esc(status.money_word || "test units")} (${esc(p.tier)})</p>
      <p><b>${t("goal_l")}:</b> ${p.target_units} · ${t("reserve")} ${p.reserve_units}</p>
      <p><a class="button" href="#buy=${r.hash}">${t("open_product")}</a></p>` : `<ul>${(d.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`) + "</div>";
}

// ---- buyer ---------------------------------------------------------------------------------------------------------
async function loadCrossings(el, withTitle) {
  try {
    const { crossings } = await api("/api/crossings");
    el.innerHTML = (withTitle ? `<h2>${t("buy_t")}</h2><p class="muted">${t("buy_none")}</p>` : "") + (crossings.length ?
      "<ul class='plist'>" + crossings.map((c) => `<li><a class="p" ${c.report ? `href="#buy=${esc(c.report)}"` : ""}>${c.verdict === "OPEN" ? `<span class="v">${t("open_v")}</span><br>` : ""}<b>${esc((c.idea || c.ref || "").slice(0, 90))}</b> <span class="small muted">· ${esc(c.verdict || c.status)}</span></a></li>`).join("") + "</ul>" :
      `<p class="empty">${t("empty")}</p>`);
    $("buyBox").hidden = true; $("tracker").hidden = true;
  } catch (e) { err(e); }
}
async function loadProduct(h) {
  try {
    const r = await api("/api/report?hash=" + h); report = r;
    const d = r.decision || {}, p = d.plan || {}, rs = r.research;
    $("productCard").innerHTML = `<p class="small muted">${esc(r.label)}</p><h1>${esc(r.idea)}</h1>` +
      (rs ? `<p class="small">${esc(rs.title)} (${esc(rs.year)}; cited ${esc(rs.cited_by_count)})${rs.regulator ? ` · <b>${esc(rs.regulator)}</b>` : ""} <a href="${esc(rs.proven_result.source || "#")}" target="_blank" rel="noopener">→</a></p>` : "") +
      (p.who ? `<div class="grid"><div><h3>${t("for_l")}</h3><p>${esc((p.who.age || "").replace(/_/g, " "))}, ${esc(p.who.gender)}</p><p class="small muted">${esc((p.who.segments || []).join(", "))}</p></div>
        <div><h3>${t("where_l")}</h3><p>${esc((p.where || []).join(", "))}</p></div><div><h3>${t("price_l")}</h3><p>${p.unit_price} / ${esc(p.tier)}</p></div>
        <div><h3>${t("goal_l")}</h3><p>${t("target")} ${p.target_units} · ${t("reserve")} ${p.reserve_units}</p></div></div>` +
        (p.unserved_audience && p.unserved_audience.length ? `<p class="small">${t("unserved_l")}: ${esc(p.unserved_audience.join(", "))}</p>` : "")
        : `<div class="decision ${esc((d.verdict || "").toLowerCase())}">${esc((d.reasons || []).join("; "))}</div>`);
    $("buyBox").hidden = d.verdict !== "OPEN";
    loadWallet();
    if (r.limits) $("productCard").insertAdjacentHTML("beforeend", `<p class="small muted">${esc(r.limits)}</p>`);
    const all = [...(r.matches || []).map((m) => ({ ...m, kept: true })), ...(r.unrelated || []).map((u) => ({ name: u.name, kept: false }))];
    if (all.length) $("productCard").insertAdjacentHTML("beforeend",
      `<details class="small"><summary>Show all Qloo matches (${all.length})</summary>` +
      all.map((m) => `<p class="small">${esc(m.name)} <span class="muted">${m.kept ? "counted" : "left out: " + esc(m.why || "shares too few of the idea's words")}</span></p>`).join("") + "</details>");
    if (r.fees && r.fees.text) $("feeLine").textContent = r.fees.text + ".";
    const action = `${location.origin}/api/actions/preorder?report=${r.hash}`;
    $("blinkLink").href = "https://dial.to/?action=" + encodeURIComponent("solana-action:" + action) + "&cluster=devnet";
    $("tracker").hidden = false;
    const res = r.reserve || {};
    $("trackList").innerHTML = (res.reserve_units ? `<li>${t("reserve")}: ${res.pre_ordered_units} / ${res.reserve_units} <progress max="${res.reserve_units}" value="${Math.min(res.pre_ordered_units, res.reserve_units)}"></progress></li>` : "") +
      ((r.preorders || []).map((o) => `<li>${esc(o.units)} · <b>${esc(o.status)}</b> · <a href="${X(o.order, "address")}" target="_blank" rel="noopener">${short(o.order)}</a></li>`).join("") || `<li class="muted">${t("empty")}</li>`);
  } catch (e) { err(e); }
}
function receipt(p) {
  const sigs = p.signatures || {};
  $("receipt").innerHTML = `<div class="decision open"><h3>${t("receipt_t")}</h3><p class="testmoney">${t("test_money")}</p><p>${esc(p.units)} · <a href="${X(p.commitment, "address")}" target="_blank" rel="noopener">${short(p.commitment)}</a></p>` +
    Object.entries(sigs).map(([k, s]) => `<p class="small">${esc(k.replace(/_/g, " "))}: <a href="${X(s)}" target="_blank" rel="noopener">${short(s)}</a>${p.finality && p.finality[k] ? ` <span class="muted">· final in ${p.finality[k].final_ms} ms (${esc(p.finality[k].commitment)})</span>` : ""}</p>`).join("") +
    (p.verified && p.verified.chain_pin ? `<p class="small">${t("evidence_pin")}: <span class="mono">${esc(p.verified.chain_pin.slice(0, 16))}…</span><br>${t("page_sha")}: <span class="mono">${esc((p.verified.sha256 || "").slice(0, 16))}…</span></p>` : "") +
    (p.verifier ? `<p class="small muted">${esc(p.verifier)}</p>` : "") +
    `<p class="small muted">${t("claim_id")}: <span class="mono">${esc(p.claim_id)}</span></p></div>`;
}
async function loadWeb3() {
  if (window.solanaWeb3) return window.solanaWeb3;
  await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "https://unpkg.com/@solana/web3.js@1.98.0/lib/index.iife.min.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  return window.solanaWeb3;
}
async function walletPreorder() {
  const w = window.phantom && window.phantom.solana || window.solflare || window.solana;
  if (!w) { window.open($("blinkLink").href, "_blank"); throw new Error("No wallet here: the Blink opened in a new tab."); }
  const web3 = await loadWeb3(); await w.connect(); const account = w.publicKey.toString();
  const r = await fetch(`/api/actions/preorder?report=${report.hash}&units=${parseInt($("units").value, 10)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ account }) });
  const a = await r.json(); if (!r.ok) throw new Error(a.message || "failed");
  const tx = web3.Transaction.from(Uint8Array.from(atob(a.transaction), (c) => c.charCodeAt(0)));
  const signed = await w.signTransaction(tx);
  const sig = await new web3.Connection("https://api.devnet.solana.com", "confirmed").sendRawTransaction(signed.serialize());
  receipt({ units: $("units").value, commitment: a.commitment, signatures: { lock: sig }, claim_id: a.claim_id || "…" });
  setTimeout(() => loadProduct(report.hash), 8000);
}

// ---- funder --------------------------------------------------------------------------------------------------------
async function loadFund() {
  try {
    const { commitments } = await api("/api/commitments");
    const open = commitments.filter((c) => c.status === "locked");
    $("fundList").innerHTML = open.map((c) => `<li class="card"><b>${esc((c.idea || "").slice(0, 80))}</b> · ${esc(c.units)} × ${esc(c.unit_price)} · <a href="${X(c.commitment, "address")}" target="_blank" rel="noopener">${short(c.commitment)}</a>
      <div class="row"><input class="fu" data-r="${esc(c.report)}" type="number" min="5" value="10" aria-label="${t("units")}" style="max-width:110px"><button class="fundBtn" data-r="${esc(c.report)}" type="button">${t("fund_btn")}</button></div>
      ${c.factoring ? `<p class="small muted">${t("factoring_t")}: ${esc(factorNote(c.factoring))}</p>` : ""}</li>`).join("") || `<li class="empty">${t("empty")}</li>`;
    document.querySelectorAll(".fundBtn").forEach((b) => b.onclick = async () => {
      const card = b.closest("li"); card.querySelectorAll(".note").forEach((n) => n.remove());
      const put = (cls, html) => card.insertAdjacentHTML("beforeend", `<div class="note ${cls}" role="status">${html}</div>`);
      if (!session) { $("signin").hidden = false; $("pkNew").focus(); put("err", esc(t("err_signin"))); return; }
      const was = b.textContent; b.disabled = true; b.textContent = t("loading") + "…";
      try {
        const units = parseInt(card.querySelector(".fu").value, 10);
        const got = await KnosPasskey.approve(await api("/api/fund", { report: b.dataset.r, units }), api);
        const sig = (got.signatures || {}).lock;
        put("ok", `✓ ${esc(got.units)} · <a href="${X(got.commitment, "address")}" target="_blank" rel="noopener">escrow ${short(got.commitment)} ↗</a>` +
          (sig ? ` · <a href="${X(sig)}" target="_blank" rel="noopener">tx ${short(sig)} ↗</a>` : "") + ` · <span class="testmoney">${t("test_money")}</span>`);
      } catch (e) { put("err", esc(e.message)); } finally { b.disabled = false; b.textContent = was; }
    });
    loadLend();
  } catch (e) { err(e); }
}
// ---- lender: receivables, as PayFi receivable financing (advance rate, fee, due date, repaid by the release) ----------
async function loadLend() {
  const { receivables } = await api("/api/receivables");
  $("lendTable").querySelector("tbody").innerHTML = receivables.map((r) => { const f = r.factoring || {}; const st = f.status || "open";
    const act = r.status !== "locked" && st !== "advanced" && st !== "assigned" ? "" :
      st === "assigned" ? `<button class="lendGo" data-go="advance" data-c="${esc(r.commitment)}" type="button">${t("pay_adv")}</button>` :
      st === "advanced" ? `<button class="lendGo quiet" data-go="collect" data-c="${esc(r.commitment)}" type="button">${t("collect_btn")}</button>` :
      `<input class="ar" type="number" min="50" max="98" value="90" aria-label="${t("adv_rate")}" style="max-width:64px">% <button class="lendGo" data-go="quote" data-c="${esc(r.commitment)}" type="button">${t("quote_btn")}</button>`;
    const q = (r.quotes || []).slice(-1)[0];
    return `<tr><td>${esc((r.idea || "").slice(0, 40))}<br><span class="muted">${esc(st)}</span></td><td>${esc(r.face_units)}</td><td>${esc(r.due)}</td>
      <td>${q ? esc(q.advance_bps / 100) + "%" : "—"}</td><td>${q ? esc(q.advance_units) : "—"}</td><td>${q ? esc(q.fee_units) + " (" + esc(q.fee_pct) + "%)" : "—"}</td><td>${act}</td></tr>`; }).join("") ||
    `<tr><td colspan="7" class="empty">${t("empty")}</td></tr>`;
  document.querySelectorAll(".lendGo").forEach((b) => b.onclick = () => busy(b, t("pk_sign"), async () => {
    if (!session) { $("signin").hidden = false; throw new Error(t("err_signin")); }
    const c = b.dataset.c;
    if (b.dataset.go === "quote") await api("/api/lend/quote", { commitment: c, advance_bps: Math.round(parseFloat(b.closest("tr").querySelector(".ar").value) * 100) });
    else receipt(await KnosPasskey.approve(await api("/api/lend/" + b.dataset.go, { commitment: c }), api));
    loadLend(); }));
}
async function loadWallet() {
  if (!session || session.kind !== "passkey") { $("pkWallet").hidden = true; return; }
  try { const w = await api("/api/wallet", {}); $("pkWallet").hidden = false; $("pkVault").textContent = short(w.vault); $("pkVault").href = w.explorer; $("pkUnits").textContent = w.balance_units; }
  catch (e) { $("pkWallet").hidden = true; }
}
// server notes the page knows are shown in the reader's language (the server's English stays in the API)
function viaLabel(c) { return { preorder: t("via_preorder"), funder: t("via_funder"), blink: t("via_blink") }[c.via_kind] || c.via || ""; }
function factorNote(f) {
  if (f.status === "quoted") return t("factoring_sim");
  if (["assigned", "advanced", "repaid"].includes(f.status)) return `${t("factoring_ready")} (${f.status})`;
  return `${f.status || ""}. ${f.note || ""}`;
}
function receiptInto(el, p) {
  el.insertAdjacentHTML("beforeend", `<p class="small">✓ ${esc(p.units)} → <a href="${X(p.commitment, "address")}" target="_blank" rel="noopener">${short(p.commitment)}</a>${(p.signatures || {}).lock ? ` · <a href="${X(p.signatures.lock)}" target="_blank" rel="noopener">${short(p.signatures.lock)}</a>` : ""}</p>`);
}

// ---- contributor ---------------------------------------------------------------------------------------------------
async function loadTasks() {
  try {
    const got = await api("/api/tasks");
    const box = $("taskBox");
    box.innerHTML = (got.rounds && got.rounds.length ? got.rounds.map((r) => { const s = r.submit || {}; return `<div class="card"><div class="row spread"><h3>${esc(r.title || r.id)}</h3><span class="testmoney">${t("test_money")}</span></div>
      <p class="small muted">${esc(r.label || "")}</p>
      <p><b>What to submit:</b> ${esc(s.what || "")}. Start from <a href="${esc(s.baseline || "#")}" target="_blank" rel="noopener">${esc(s.file || "train.py")}</a> and read the <a href="${esc(s.readme || "#")}" target="_blank" rel="noopener">task's README</a>.</p>
      <p class="small muted">Round ${esc(r.round)} · ${esc(String(r.players ?? 0))} players · up to ${esc(s.attempts_per_round)} attempts per round · ${esc(s.time_budget_s)} s per run · ${esc(s.prize || "")}</p>
      <label for="tn-${esc(r.id)}">Your name</label><input id="tn-${esc(r.id)}" class="tname" data-g="${esc(r.id)}" maxlength="40" placeholder="ada">
      <label for="tw-${esc(r.id)}">Payout wallet (devnet, optional)</label><input id="tw-${esc(r.id)}" class="twal" data-g="${esc(r.id)}" maxlength="44" placeholder="Solana address">
      <label for="ts-${esc(r.id)}">The whole ${esc(s.file || "train.py")}</label><textarea id="ts-${esc(r.id)}" class="tsub mono" data-g="${esc(r.id)}" rows="8" maxlength="100000"></textarea>
      <button class="tBtn" data-g="${esc(r.id)}" type="button">Submit work</button></div>`; }).join("") :
      `<p class="note">${t("contribute_none")} ${esc(got.why || "")}</p>`) +
      (got.milestones && got.milestones.length ? `<ul class="list">` + got.milestones.map((m) => `<li>${esc((m.idea || "").slice(0, 70))} · <span class="mono small">${esc(m.claim_id)}</span> · <a href="#make">${t("milestone_prove")}</a></li>`).join("") + "</ul>" : "");
    document.querySelectorAll(".tBtn").forEach((b) => b.onclick = async () => {
      const card = b.closest(".card"); card.querySelectorAll(".note").forEach((n) => n.remove());
      const put = (cls, html) => card.insertAdjacentHTML("beforeend", `<div class="note ${cls}" role="status">${html}</div>`);
      if (!session) { $("signin").hidden = false; $("pkNew").focus(); put("err", esc(t("err_signin"))); return; }
      const g = b.dataset.g, was = b.textContent; b.disabled = true; b.textContent = "Judging…";
      try {
        const out = await api("/api/task/submit", { round: g, name: card.querySelector(".tname").value, wallet: card.querySelector(".twal").value || undefined, code: card.querySelector(".tsub").value });
        const r = out.result || {}, pz = out.prize;
        put(r.decision === "scored" ? "ok" : "", `<b>${esc(out.name)}</b>, attempt ${esc(r.n)}: <b>${esc(r.decision)}</b>${r.shown != null ? ` · shown score ${esc(r.shown)}` : ""}` +
          (r.reasons && r.reasons.length ? `<br><span class="small">${esc(r.reasons.join("; "))}</span>` : "") +
          `<br><span class="small mono">sha256 ${esc(String(r.sha256 || "").slice(0, 16))}… (your file: ${esc(out.submitted_sha256.slice(0, 16))}…)</span>` +
          (pz ? `<br>${pz.paid ? `Prize: ${esc(pz.units)} test units → <a href="${esc((pz.explorer || []).slice(-1)[0] || "#")}" target="_blank" rel="noopener">release ↗</a>` :
            pz.status === "signing" ? `<span class="prizeSigning">Prize: ${esc(pz.units)} test units locked (<a href="${esc((pz.explorer || [])[0] || "#")}" target="_blank" rel="noopener">tx ↗</a>), funded by the round's sponsor; released when 2 of 3 referee hosts sign (session <span class="mono">${esc(String(pz.session).slice(0, 8))}</span>)</span>` :
            `Prize not paid: ${esc(pz.why || "")}`}` : ""));
      } catch (e) { put("err", esc(e.message)); } finally { b.disabled = false; b.textContent = was; }
    });
  } catch (e) { err(e); }
}

// ---- maker ---------------------------------------------------------------------------------------------------------
async function loadMaker() {
  try {
    const { commitments } = await api("/api/commitments");
    $("makeList").innerHTML = commitments.map((c) => `<li class="card"><b>${esc((c.idea || "").slice(0, 80))}</b> · ${esc(c.units)} × ${esc(c.unit_price)} · <b>${esc(c.status)}</b>
      <p class="small"><a href="${X(c.commitment, "address")}" target="_blank" rel="noopener">${short(c.commitment)}</a> · <span class="mono">${esc(c.claim_id)}</span> · ${esc(viaLabel(c))}</p>
      ${Object.entries(c.signatures || {}).map(([k, s]) => `<span class="small">${esc(k.replace(/_/g, " "))}: <a href="${X(s)}" target="_blank" rel="noopener">${short(s)}</a></span>`).join(" · ")}
      ${c.status === "locked" ? `<label>${t("evidence_url")}</label><div class="row"><input class="ev" data-c="${esc(c.commitment)}" type="url" placeholder="https://…"><button class="msBtn" data-c="${esc(c.commitment)}" type="button">${t("milestone_prove")}</button></div>` : ""}
      ${c.factoring ? `<p class="small muted">${t("factoring_t")}: ${esc(factorNote(c.factoring))}</p>` : ""}
      ${c.status === "locked" && c.factoring && c.factoring.status === "quoted" ? (c.factoring.quotes || []).map((q) => `<button class="acBtn quiet" data-c="${esc(c.commitment)}" data-q="${esc(q.id)}" type="button">${t("accept_btn")}: ${esc(q.advance_units)} (${esc(q.advance_bps / 100)}%)</button>`).join(" ") : ""}</li>`).join("") || `<li class="empty">${t("empty")}</li>`;
    document.querySelectorAll(".acBtn").forEach((b) => b.onclick = () => busy(b, t("pk_sign"), async () => {
      if (!session) { $("signin").hidden = false; throw new Error(t("err_signin")); }
      receipt(await KnosPasskey.approve(await api("/api/factor", { commitment: b.dataset.c, quote: b.dataset.q }), api)); loadMaker(); }));
    document.querySelectorAll(".msBtn").forEach((b) => b.onclick = () => busy(b, t("loading"), async () => {
      if (!session) { $("signin").hidden = false; throw new Error(t("err_signin")); }
      const url = document.querySelector(`.ev[data-c="${b.dataset.c}"]`).value;
      const got = await api("/api/milestone", { commitment: b.dataset.c, evidence_url: url });
      receipt(got); loadMaker(); }));
  } catch (e) { err(e); }
}

// ---- agents --------------------------------------------------------------------------------------------------------
async function loadAgents() {
  $("mcpUrl").textContent = location.origin + "/mcp";
  const box = $("memBox");
  if (box && !box.dataset.wired) {
    box.dataset.wired = "1";
    box.querySelector("input").placeholder = t("mem_search");
    box.querySelector("form").onsubmit = async (ev) => {
      ev.preventDefault(); const out = box.querySelector(".memOut");
      out.innerHTML = `<span class="spin"></span>`;
      try {
        const g = await api("/api/memory/search?q=" + encodeURIComponent(box.querySelector("input").value));
        out.innerHTML = `<p class="small muted">${esc(g.said || "")}</p>` +
          (g.rows || []).map((r) => `<p class="small"><span class="tag">${esc(r.tier || "")}</span>${esc(r.name || r.key || r.doc_key || "")} <span class="muted">${esc((r.snippet || "").slice(0, 140))}</span></p>`).join("");
      } catch (e) { out.innerHTML = `<p class="small muted">${esc(e.message)}</p>`; }
    };
  }
  try {
    const r = await fetch("/mcp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }) });
    const j = await r.json();
    $("mcpTools").innerHTML = ((j.result || {}).tools || []).map((x) => `<p><b class="mono">${esc(x.name)}</b><br><span class="small muted">${esc(x.description)}</span></p>`).join("");
  } catch (e) { $("mcpTools").innerHTML = ""; }
}

// ---- boot ----------------------------------------------------------------------------------------------------------
async function boot() {
  langMenu(); applyLang();
  const h = location.hash;
  const m = h.match(/session=([^&]+)/);
  if (m) { try { const tok = decodeURIComponent(m[1]); const b = tok.split(".")[0]; const pad = b + "===".slice((b.length + 3) % 4); setSession({ token: tok, ...JSON.parse(atob(pad.replace(/-/g, "+").replace(/_/g, "/"))) }); } catch (e) { } history.replaceState(null, "", "#research"); }
  const mg = h.match(/magic=([^&]+)/);
  if (mg) { try { setSession(await api("/api/auth/email/verify", { token: decodeURIComponent(mg[1]) })); } catch (e) { err(e); } history.replaceState(null, "", "#research"); }
  setSession(session);
  try {
    status = await api("/api/status");
    const rest = status.qloo_rest || {};
    $("modeBadge").textContent = rest.rest ? t("status_live") : t("status_off");
    $("modeBadge").className = "badge " + (rest.rest ? "live" : "off");
    const a = status.auth || {};
    if (a.google_client_id) google(a.google_client_id);
    $("orcidBtn").hidden = !a.orcid;
    if (!a.passkey || !window.PublicKeyCredential) { $("pkNew").disabled = $("pkUse").disabled = true; }
    $("emailNote").textContent = a.email_note || "";
  } catch (e) { err(e); }
  show();
}
$("whoBtn").onclick = () => { const sh = $("signin"); sh.hidden = !sh.hidden; if (!sh.hidden) ($("pkNew").disabled ? $("email") : $("pkNew")).focus(); };
$("signinClose").onclick = () => { $("signin").hidden = true; $("whoBtn").focus(); };
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("signin").hidden) { $("signin").hidden = true; $("whoBtn").focus(); } });
$("outBtn").onclick = () => setSession(null);
$("pkNew").onclick = () => busy($("pkNew"), t("loading"), passkeyNew);
$("pkUse").onclick = () => busy($("pkUse"), t("loading"), passkeyUse);
$("emailBtn").onclick = () => busy($("emailBtn"), t("loading"), emailGo);
document.querySelectorAll(".chip").forEach((c) => c.onclick = () => { $("ref").value = c.dataset.ref; });
$("crossForm").onsubmit = (ev) => { ev.preventDefault(); busy($("crossBtn"), t("cross_busy"), cross); };
$("walletBtn").onclick = () => busy($("walletBtn"), t("loading"), walletPreorder);
$("preBtn").onclick = () => busy($("preBtn"), t("loading"), async () => {
  if (!session) { $("signin").hidden = false; throw new Error(t("err_signin")); }
  const step = await api("/api/preorder", { report: report.hash, units: parseInt($("units").value, 10) });
  const p = await KnosPasskey.approve(step, api); receipt(p); loadProduct(report.hash); });
$("faucetBtn").onclick = () => busy($("faucetBtn"), t("loading"), async () => { await api("/api/wallet/faucet", {}); loadWallet(); });
$("claimBtn").onclick = () => busy($("claimBtn"), t("loading"), async () => {
  if (!session) { $("signin").hidden = false; throw new Error(t("err_signin")); }
  const c = await api("/api/maker/claim", { report: report.hash }); $("claimNote").textContent = `${t("claimed")}: ${c.maker} · ${short(c.main_wallet)}`; });
boot();
