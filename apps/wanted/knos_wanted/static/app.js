// Knos demand check: the page. No framework, no key: every Qloo call happens on the server.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let session = null, report = null, calls = [];
try { session = JSON.parse(localStorage.getItem("knos.session") || "null"); } catch (e) { session = null; }

async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (session && session.token) headers.Authorization = "Bearer " + session.token;
  const r = await fetch(path, body === undefined ? { headers } : { method: "POST", headers, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
  return data;
}
function err(e) { const b = $("err"); b.hidden = !e; b.textContent = e ? String(e.message || e) : ""; if (e) b.scrollIntoView({ block: "nearest" }); }
let slowTimer = null, card = null;
function slow(on, what) {
  clearTimeout(slowTimer); const el = $("slow");
  if (!on) { el.hidden = true; return; }
  el.hidden = false; el.textContent = what + "...";
  slowTimer = setTimeout(() => { el.textContent = what + "... still working: a free server can take up to a minute to wake, and Qloo answers take a few seconds each."; }, 6000);
}
function busy(btn, on, text) { slow(on, (text || "").replace(/\.+$/, "")); btn.disabled = on; if (on) { btn.dataset.t = btn.textContent; btn.textContent = text; } else if (btn.dataset.t) btn.textContent = btn.dataset.t; }
function src(n) { const c = calls[n - 1]; return n && c ? `<span class="src" title="${esc(JSON.stringify(c.params))}">source #${n} ${esc(c.call)}${c.params && c.params["filter.type"] ? " " + esc(c.params["filter.type"]) : ""}</span>` : ""; }
function pct(v) { return v == null ? "?" : (Math.round(v * 1000) / 10) + "%"; }
function tx(sig) { return `<a href="https://explorer.solana.com/tx/${esc(sig)}?cluster=devnet" target="_blank" rel="noopener">${esc(sig.slice(0, 10))}...</a>`; }

// ---- sign in ------------------------------------------------------------------------------------------------------
function b64u(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function unb64u(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); const b = atob(s + "===".slice((s.length + 3) % 4)); return Uint8Array.from(b, (c) => c.charCodeAt(0)); }
function setSession(s) {
  session = s; try { s ? localStorage.setItem("knos.session", JSON.stringify(s)) : localStorage.removeItem("knos.session"); } catch (e) { /* private mode */ }
  $("whoBtn").textContent = s ? s.label : "Sign in"; $("outBtn").hidden = !s;
  if (s) $("signin").hidden = true;
}
async function passkeyNew() {
  const ch = await api("/api/auth/challenge", {});
  const label = $("email").value.trim() || "Knos user";
  const cred = await navigator.credentials.create({ publicKey: {
    challenge: unb64u(ch.challenge), rp: { name: "Knos", id: ch.rp_id },
    user: { id: crypto.getRandomValues(new Uint8Array(16)), name: label, displayName: label },
    pubKeyCredParams: [{ type: "public-key", alg: -7 }], attestation: "none", timeout: 60000,
    authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" } } });
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
  s.onload = () => {
    window.google.accounts.id.initialize({ client_id: clientId, callback: async (r) => { try { setSession(await api("/api/auth/google", { credential: r.credential })); err(null); } catch (e) { err(e); } } });
    window.google.accounts.id.renderButton($("gsi"), { theme: "outline", size: "large", width: 280 });
  };
  document.head.appendChild(s);
}

// ---- the report ---------------------------------------------------------------------------------------------------
const VERDICT = { OPEN: "Pre-orders open", REFUSE: "Refused", CANNOT_DECIDE: "Cannot decide" };
function bars(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `<div class="bar"><span>${esc(k.replace(/_/g, " "))}</span><i style="--w:${Math.round(Math.abs(v) * 100)}%" class="${v < 0 ? "neg" : ""}"></i><b>${v > 0 ? "+" : ""}${Math.round(v * 100) / 100}</b></div>`).join("");
}
function render(r) {
  report = r; calls = r.calls || []; $("report").hidden = false;
  const d = r.decision || {};
  $("decision").className = "card decision " + (d.verdict || "").toLowerCase();
  $("decision").innerHTML = `<p class="label">${esc(r.label)}</p><h2>${esc(VERDICT[d.verdict] || d.verdict)}</h2>` +
    (d.verdict === "OPEN" ? `<p class="big">Target <b>${d.target_units}</b> units, reserve <b>${d.reserve_units}</b> before the maker is paid</p><p class="mono small">${esc(d.formula)}</p>` : "") +
    `<ul>${(d.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="muted small">Decided by code from the numbers below (rules at the bottom); no language model decides. Report ${esc((r.hash || "").slice(0, 16))}</p>`;
  const w = r.who, na = r.named_audience || [];
  $("who").innerHTML = `<h3>Who</h3>` + (w ? `<p>Strongest: <b>${esc((w.top_age || "").replace(/_/g, " "))}</b>, <b>${esc(w.top_gender)}</b></p>${bars(w.age)}${bars(w.gender)}` +
    na.map((a) => { const v = ((w[a.dimension] || {})[a.key]); return `<p class="${v < 0 ? "warn" : ""}">You named <b>${esc(a.word)}</b>: Qloo scores ${esc(a.key.replace(/_/g, " "))} ${v == null ? "?" : (v > 0 ? "+" : "") + v}${v < 0 ? " (leans away)" : ""}</p>`; }).join("") + src(w.src) : `<p class="muted">No demographic signal.</p>`);
  const pl = r.places || [], pts = r.where || [];
  $("where").innerHTML = `<h3>Where${r.place ? " in " + esc(r.place) : ""}</h3>` +
    (pl.length ? `<ol>${pl.map((p) => `<li><b>${esc(p.name)}</b>${p.area ? " <span class=\"muted\">" + esc(p.area) + "</span>" : ""}</li>`).join("")}</ol>${src(pl[0].src)}` : "") +
    (pts.length ? `<p class="small">Hot spots on the map: ${pts.map((p, i) => `<a href="https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=12/${p.lat}/${p.lon}" target="_blank" rel="noopener">area ${i + 1}</a>`).join(", ")}</p>${src(pts[0].src)}` : "") +
    (pl.length || pts.length ? "" : `<p class="muted">No place data.</p>`);
  $("aud").innerHTML = `<h3>Audience segments</h3>` + ((r.audiences || []).length ? `<ul>${r.audiences.map((a) => `<li>${esc(a.name)} <b>${pct(a.affinity)}</b>${a.affinity > 0.55 ? "" : " <span class=\"muted\">(neutral)</span>"}</li>`).join("")}</ul><p class="muted small">50% is Qloo's neutral value: only segments above 55% count.</p>${src(r.audiences[0].src)}` : `<p class="muted">None.</p>`);
  const t = r.trend || {};
  $("trend").innerHTML = `<h3>Rising or falling?</h3><p class="big">${esc(t.direction || "unknown")}</p>` +
    (t.data_through ? `<p>${esc(t.entity)}: weekly percentile ${t.start_percentile} to ${t.end_percentile}, ${esc(t.from)} to ${esc(t.to)}. Data through ${esc(t.data_through)}.</p>` : "") +
    (t.why ? `<p class="muted">${esc(t.why)}.</p>` : "") + src(t.src);
  const v = r.versus;
  $("versus").innerHTML = `<h3>Versus the leader${r.leader ? ": " + esc(r.leader.name) : ""}</h3>` + (v ? `<p>Overlap <b>${pct(v.overlap)}</b> <span class="muted">(${esc(v.method)})</span></p><p><b>Shared:</b> ${esc(v.shared.join(", ") || "none")}</p><p><b>Your opening:</b> ${esc(v.whitespace.join(", ") || "none")}</p><p><b>Leader only:</b> ${esc(v.leader_only.join(", ") || "none")}</p>${src(v.src)}` : `<p class="muted">No comparison was possible; that never lets pre-orders open.</p>`);
  $("matches").innerHTML = `<h3>Closest existing products</h3>` + ((r.matches || []).length ? `<p class="small muted">Untick any that are not like your idea, then decide again.</p><ul class="picks">${r.matches.map((m) => `<li><label><input type="checkbox" checked value="${esc(m.id)}"> ${esc(m.name)}</label> <span class="muted">popularity ${pct(m.popularity)}; shares: ${esc((m.matched_words || []).join(", "))}${m.located ? "; " + esc(m.located) : ""}</span></li>`).join("")}</ul><button type="button" id="redo" class="ghost">Decide again without the unticked</button>${src(r.matches[0].src)}` : `<p class="muted">None that relate to the idea.</p>`) +
    ((r.unrelated || []).length ? `<p class="small muted">Left out (too few shared words): ${r.unrelated.map((u) => esc(u.name)).join(", ")}</p>` : "") +
    ((r.tags || []).length ? `<p><b>Taste tags:</b> ${r.tags.map((x) => esc(x.name)).join(", ")}</p>${src(r.tags[0].src)}` : "");
  const redo = $("redo"); if (redo) redo.onclick = () => runCheck([...(r.excluded || []).map((m) => m.id), ...[...document.querySelectorAll(".picks input:not(:checked)")].map((i) => i.value)]);
  $("calls").innerHTML = calls.map((c) => `<li><b>${esc(c.call)}</b> ${esc(c.what)} <span class="muted">${c.error ? "failed: " + esc(c.error) : c.cached ? "cached " + esc(c.at) : "live " + esc(c.at)}</span></li>`).join("");
  $("rules").textContent = "Rules: " + JSON.stringify(r.rules || {});
  if (r.fees && r.fees.text) $("feeLine").textContent = r.fees.text + ".";
  $("pre").hidden = d.verdict !== "OPEN";
  if (d.verdict === "OPEN") { $("units").max = d.target_units; $("preModel").textContent = (r.fees && r.fees.text) || ""; }
  const rs = r.research;
  if (rs) $("decision").insertAdjacentHTML("beforeend", `<h3>Why it never crossed the valley</h3><ul>${(rs.why_never_crossed || []).map((w) => `<li class="${w.flag ? "warn" : ""}"><b>${esc(w.wall)}</b>: ${esc(w.evidence)}</li>`).join("")}</ul>`);
  try { history.replaceState(null, "", "#report=" + r.hash); } catch (e) { /* file */ }
  if (d.verdict === "OPEN") loadPre(r.hash);
}
async function loadPre(hash) {
  const r = await api("/api/report?hash=" + encodeURIComponent(hash));
  const res = r.reserve || {};
  $("reserve").innerHTML = res.reserve_units ? `<p>Reserve: <b>${res.pre_ordered_units}</b> of <b>${res.reserve_units}</b> units pre-ordered ${res.met ? "(met: the maker can be paid on proof)" : "(the maker is paid only once it is met)"}</p><progress max="${res.reserve_units}" value="${Math.min(res.pre_ordered_units, res.reserve_units)}"></progress>` : "";
  const list = r.preorders || [];
  $("preList").innerHTML = list.map((p) => `<li>${esc(p.units)} units by ${esc(p.buyer)}: <b>${esc(p.status)}</b> <a href="https://explorer.solana.com/address/${esc(p.order)}?cluster=devnet" target="_blank" rel="noopener">escrow</a></li>`).join("");
  $("ms").hidden = !list.length;
  $("commit").innerHTML = list.map((p) => `<option value="${esc(p.order)}" data-claim="${esc(p.claim_id)}">${esc(p.units)} units, ${esc(p.status)} (${esc(p.order.slice(0, 8))})</option>`).join("");
  showClaim();
}
function showClaim() { const o = $("commit").selectedOptions[0]; $("claimId").textContent = o ? "Claim id to put on your page: " + o.dataset.claim : ""; }
function out(res) {
  const sigs = res.signatures || {};
  return `<p>Status: <b>${esc(res.release || res.status)}</b></p><ul>${Object.entries(sigs).map(([k, s]) => `<li>${esc(k.replace(/_/g, " "))}: ${tx(s)}</li>`).join("")}</ul>` +
    (res.verified ? `<p class="small">Evidence verified: ${esc(res.verified.url)} (sha256 ${esc(res.verified.sha256.slice(0, 16))})</p>` : "") +
    `<p class="muted small">${esc(res.panel ? res.panel.label + ": " + res.panel.note : "")}</p>`;
}

// ---- wiring -------------------------------------------------------------------------------------------------------
async function boot() {
  setSession(session);
  try {
    const s = await api("/api/status");
    const rest = s.qloo_rest || {};
    $("modeBadge").textContent = rest.rest ? "Qloo: live" : "Qloo: off";
    $("modeBadge").className = "badge " + (rest.rest ? "live" : "off");
    $("modeBadge").title = rest.rest ? `Qloo's API, read on this server (${rest.calls_this_month} of ${rest.budget} calls this month)` : rest.reason;
    if (s.fees && s.fees.text) $("feeLine").textContent = s.fees.text + ".";
    const a = s.auth || {};
    if (a.google_client_id) google(a.google_client_id);
    if (!a.passkey || !window.PublicKeyCredential) { $("pkNew").disabled = $("pkUse").disabled = true; $("pkNote").textContent = "Passkeys are not available here."; }
    if (a.email_note) $("emailNote").textContent = a.email_note + ".";
  } catch (e) { err(e); }
  await fromHash();
}
async function fromHash() {
  const m = location.hash.match(/report=([0-9a-f]{64})/);
  if (m && (!report || report.hash !== m[1])) { try { render(await api("/api/report?hash=" + m[1])); } catch (e) { err(e); } }
}
window.addEventListener("hashchange", fromHash);
async function runCheck(exclude) {
  err(null); const b = $("checkBtn"); busy(b, true, "Asking Qloo...");
  try { render(await api("/api/check", { idea: $("idea").value, place: $("place").value, leader: $("leader").value, research: card && $("idea").value === card.product ? card.hash : undefined, exclude: exclude || [] })); $("decision").scrollIntoView({ behavior: "smooth" }); }
  catch (e) { err(e); } finally { busy(b, false); }
}
$("whoBtn").onclick = () => { $("signin").hidden = !$("signin").hidden; if (!$("signin").hidden) $("signin").scrollIntoView({ block: "nearest" }); };
$("outBtn").onclick = () => setSession(null);
$("pkNew").onclick = async () => { try { err(null); await passkeyNew(); } catch (e) { err(e); } };
$("pkUse").onclick = async () => { try { err(null); await passkeyUse(); } catch (e) { err(e); } };
$("guestBtn").onclick = async () => { try { err(null); setSession(await api("/api/auth/guest", { label: $("email").value })); } catch (e) { err(e); } };
$("commit").onchange = showClaim;
$("checkForm").onsubmit = (ev) => { ev.preventDefault(); runCheck([]); };
$("preBtn").onclick = async () => {
  if (!session) { $("signin").hidden = false; return err("Sign in first: a passkey, Google, or a label."); }
  const b = $("preBtn"); busy(b, true, "Locking on devnet..."); err(null);
  try { const r = await api("/api/preorder", { report: report.hash, units: parseInt($("units").value, 10), maker_wallet: $("maker").value || undefined });
    $("preList").insertAdjacentHTML("afterbegin", `<li class="new">${out(r)}</li>`); await loadPre(report.hash); }
  catch (e) { err(e); } finally { busy(b, false); }
};
$("msBtn").onclick = async () => {
  if (!session) { $("signin").hidden = false; return err("Sign in first."); }
  const b = $("msBtn"); busy(b, true, "Verifying..."); err(null);
  try { $("msOut").innerHTML = out(await api("/api/milestone", { commitment: $("commit").value, evidence_url: $("evidence").value })); await loadPre(report.hash); }
  catch (e) { err(e); } finally { busy(b, false); }
};
$("refundBtn").onclick = async () => {
  if (!session) { $("signin").hidden = false; return err("Sign in first."); }
  try { err(null); $("msOut").innerHTML = out(await api("/api/refund", { commitment: $("commit").value })); await loadPre(report.hash); } catch (e) { err(e); }
};
function renderCard(c) {
  card = c; const el = $("rcard"); el.hidden = false;
  const n = c.nobel, r = c.retraction || {};
  el.innerHTML = `<p class="label">${esc(c.label || "")}</p><h3>${esc(c.title)}</h3>` +
    `<p class="muted">${esc(c.field || "")}${c.year ? ", " + c.year : ""}${c.venue ? ", " + esc(c.venue) : ""}</p>` +
    `<blockquote>${esc(c.proven_result.quote)}</blockquote><p class="small muted">Proven result: ${esc(c.proven_result.where)}, <a href="${esc(c.proven_result.source || "#")}" target="_blank" rel="noopener">source</a></p>` +
    `<p>Cited <b>${c.cited_by_count == null ? "?" : c.cited_by_count.toLocaleString()}</b> times${c.cited_source ? ` (<a href="${esc(c.cited_source)}" target="_blank" rel="noopener">OpenAlex</a>)` : ""}. ` +
    `Retraction: <b>${r.retracted ? "RETRACTED" : r.checked || r.via ? "none found" : "not checked"}</b>${r.via ? " (" + esc(r.via) + ")" : ""}.</p>` +
    (n ? `<p>Nobel Prize in ${esc(n.prize)} ${n.year} (${esc(n.laureates)}): "${esc(n.said)}" <a href="${esc(n.url)}" target="_blank" rel="noopener">nobelprize.org</a></p>` : "") +
    `<p class="small muted">Product it enables: ${esc(c.product_source)}. Edit it below if you see it differently.</p>`;
  $("idea").value = c.product; $("idea").focus();
}
$("researchForm").onsubmit = async (ev) => {
  ev.preventDefault(); err(null); const b = $("refBtn"); busy(b, true, "Reading the paper...");
  try { renderCard(await api("/api/research", { ref: $("ref").value })); } catch (e) { err(e); } finally { busy(b, false); }
};
boot();
