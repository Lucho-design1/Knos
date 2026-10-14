"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 2) => (typeof n === "number" ? n.toFixed(d) : "n/a");
let maker = null, report = null, buyerS = null, lockHash = null, status = null;

const EXAMPLES = [
  { idea: "A late-night oat-milk coffee bar for students in London", variants: "", rivals: "Starbucks, Pret", place: "London" },
  { idea: "A vegan Nigerian street-food truck for young professionals in New York", variants: "", rivals: "", place: "New York" },
  { idea: "A true-crime podcast for women about unsolved art heists", variants: "", rivals: "", place: "Los Angeles" },
];

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
function showErr(msg) { const e = $("#err"); e.textContent = msg || ""; e.hidden = !msg; }
async function busy(btn, label, fn) {
  const old = btn.textContent; btn.disabled = true; btn.textContent = label; showErr("");
  try { await fn(); } catch (e) { showErr(e.message || String(e)); }
  btn.disabled = false; btn.textContent = old;
}

async function loadStatus() {
  try {
    status = await api("/api/status");
    const b = $("#modeBadge"); b.textContent = status.label; b.classList.toggle("live", status.mode === "live");
    $("#framing").textContent = status.framing;
    $("#reason").textContent = `Qloo: ${status.mode.toUpperCase()} (${status.reason}). Transport: ${status.transport}; ${status.tools.length} MCP tools listed.`;
    $("#targets").innerHTML = status.targets.map((t, i) => `<label class="tick"><input type="checkbox" value="${esc(t)}" ${i < 2 ? "checked" : ""}> ${esc(t.replace("_", " "))}</label>`).join("");
    if (!status.escrow || !status.demo_wallet) {
      $("#demoBuy").disabled = true; $("#walletBuy").disabled = true;
      $("#lockOut").textContent = !status.escrow ? "Escrow unavailable on this server (the knos package is not installed)." : "Escrow unavailable: this server has no devnet test wallet configured.";
    }
  } catch (e) { $("#modeBadge").textContent = "server unreachable"; }
}

function tab(which) {
  $("#maker").hidden = which !== "maker"; $("#buyer").hidden = which !== "buyer";
  $("#tabMaker").classList.toggle("on", which === "maker"); $("#tabBuyer").classList.toggle("on", which === "buyer");
  $("#tabMaker").setAttribute("aria-selected", which === "maker"); $("#tabBuyer").setAttribute("aria-selected", which === "buyer");
}
$("#tabMaker").addEventListener("click", () => tab("maker"));
$("#tabBuyer").addEventListener("click", () => tab("buyer"));

// ---- the trail -----------------------------------------------------------------------------------------------
function renderTrail(trail) {
  $("#trailBox").hidden = !trail?.length;
  $("#trail").innerHTML = `<table class="tbl"><tr><th>#</th><th>Step</th><th>Tool</th><th>Request (redacted: no key, no personal data)</th><th>Why</th><th>Result</th></tr>${
    trail.map((t, i) => `<tr class="${t.tool ? "" : "confirmed"}"><td>${i + 1}</td><td>${esc(t.step)}</td><td>${t.tool ? `<code>${esc(t.tool)}</code>` : "<b>you confirmed</b>"}</td>
      <td>${t.request ? `<code class="req">${esc(JSON.stringify(t.request))}</code>` : t.chosen ? `chosen: <code>${esc(t.chosen)}</code>` : ""}</td>
      <td>${esc(t.why)}</td><td>${esc(t.status)}${t.result_count != null ? ` (${esc(t.result_count)})` : ""}${t.cached ? " cached" : ""}${t.attempts > 1 ? ` after ${t.attempts} tries` : ""}${t.error ? ` ${esc(t.error)}` : ""}${t.label ? ` <span class="mockchip">MOCK</span>` : ""}</td></tr>`).join("")}</table>`;
}

// ---- questions (confirm the match) ---------------------------------------------------------------------------
function renderQs(el, s, onSearch) {
  el.innerHTML = s.questions.map((q, qi) => {
    const kindWord = { tag: "taste", proxy: "closest existing product", rival: "rival", like: "you like", vibe: "vibe" }[q.kind] || q.kind;
    const type = q.pick === "many" ? "checkbox" : "radio";
    const opts = q.candidates.map((c, ci) => `<label class="cand"><input type="${type}" name="q${qi}" value="${esc(c.id)}" ${ci === 0 && q.kind !== "tag" ? "" : ""}>
        ${esc(c.name)} <span class="cid">${esc(c.type || "")} ${esc(c.id)}</span></label>`).join("");
    return `<fieldset class="q"><legend>${esc(kindWord)}: "${esc(q.input)}" <span class="status">${esc(q.status)}${q.summary ? ": " + esc(q.summary) : ""}</span></legend>
      ${opts || "<p class='status'>Qloo found no candidate.</p>"}
      <label class="cand"><input type="${type}" name="q${qi}" value=""> none of these</label>
      ${onSearch ? `<div class="again"><input placeholder="Try another name" data-qi="${qi}"><button type="button" data-qi="${qi}">Look up</button></div>` : ""}</fieldset>`;
  }).join("");
  if (onSearch) el.querySelectorAll(".again button").forEach((b) => b.addEventListener("click", () => onSearch(Number(b.dataset.qi), el.querySelector(`.again input[data-qi="${b.dataset.qi}"]`).value, b)));
}
function choices(el, s) {
  const out = {};
  s.questions.forEach((q, qi) => {
    const picked = [...el.querySelectorAll(`input[name="q${qi}"]:checked`)].map((x) => x.value).filter(Boolean);
    if (picked.length) out[q.key] = q.pick === "many" ? picked : picked[0];
  });
  return out;
}

// ---- maker ----------------------------------------------------------------------------------------------------
$("#examples").innerHTML = EXAMPLES.map((e, i) => `<button type="button" data-i="${i}">${esc(e.idea.slice(0, 40))}...</button>`).join("");
$("#examples").addEventListener("click", (ev) => {
  const i = ev.target?.dataset?.i; if (i == null) return;
  const e = EXAMPLES[i]; $("#idea").value = e.idea; $("#variants").value = e.variants; $("#rivals").value = e.rivals; $("#place").value = e.place;
});
function makerSearch(qi, name, btn) {
  return busy(btn, "...", async () => {
    const r = await api("/api/maker/search", { session: maker.id, key: maker.questions[qi].key, name });
    maker.questions[qi] = r.question; maker.trail = r.trail;
    renderQs($("#makerQs"), maker, makerSearch); renderTrail(maker.trail);
  });
}
$("#makerForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  busy($("#makerGo"), "Asking Qloo...", async () => {
    maker = await api("/api/maker/start", { idea: $("#idea").value, variants: $("#variants").value, rivals: $("#rivals").value, place: $("#place").value });
    $("#report").hidden = true; $("#makerConfirm").hidden = false;
    renderQs($("#makerQs"), maker, makerSearch);
    renderTrail(maker.trail);
    $("#makerConfirm").scrollIntoView({ behavior: "smooth" });
  });
});
$("#makerConfirmGo").addEventListener("click", () => busy($("#makerConfirmGo"), "Asking Qloo...", async () => {
  report = await api("/api/maker/confirm", { session: maker.id, choices: choices($("#makerQs"), maker) });
  renderReport(report); renderTrail(report.trail);
}));

function bar(label, v, min, max, cls = "") {
  const span = max - min || 1, zero = ((0 - min) / span) * 100, pos = ((v - min) / span) * 100;
  return `<div class="barrow"><span class="lbl" title="${esc(label)}">${esc(label)}</span><span class="track"><span class="fill ${v < 0 ? "neg" : ""} ${cls}" style="left:${Math.min(zero, pos)}%;width:${Math.max(Math.abs(pos - zero), 1)}%"></span></span><span class="num">${fmt(v)}</span></div>`;
}
function fill(id, sec, html) {
  const el = document.querySelector(id);
  el.querySelector(".body").innerHTML = sec.status === "ok" ? html() : `<p class="status">${esc(sec.note || ({ needs_input: "Qloo needs a clearer input.", empty: "Qloo returned nothing.", error: "The Qloo call failed." }[sec.status] || sec.status))}</p>`;
  el.querySelector(".src").textContent = sec.source ? `Source: ${sec.source}. Aggregate taste, not a prediction about one person.` : "";
}
function renderReport(r) {
  $("#makerConfirm").hidden = true; $("#report").hidden = false;
  const lw = $("#leanWord"); lw.textContent = r.lean.word;
  lw.className = "lean-word " + ({ "leans wanted": "leans", weak: "weak", mixed: "mixed" }[r.lean.word] || "");
  $("#leanWhy").innerHTML = r.lean.why.map((w) => `<li>${esc(w)}</li>`).join("") || "<li>Not enough sections with data.</li>";
  const lab = $("#reportLabel"); lab.textContent = `${r.label}. ${r.framing} ${r.aggregate[0].toUpperCase()}${r.aggregate.slice(1)}.`; lab.classList.toggle("live", r.mode === "live");
  const chips = (xs) => xs.map((x) => `<span class="chip">${esc(x.name)}</span>`).join("") || "none";
  $("#chosen").innerHTML = `You confirmed: taste ${chips(r.chosen.tags)} | stands for the idea ${chips(r.chosen.proxies)} | rivals ${chips(r.chosen.rivals)} ${r.place ? "| place " + esc(r.place) : ""}`;
  fill("#secWho", r.who, () => {
    const m = Math.max(0.5, ...r.who.segments.map((s) => Math.abs(s.score)));
    return `<div class="bars">${r.who.segments.map((s) => bar(s.label, s.score, -m, m)).join("")}${Object.entries(r.who.gender || {}).map(([k, v]) => bar(k, v, -m, m)).join("")}</div>
      <p class="status">Above 0: this audience leans in more than average.</p>
      <p>Taste concepts: ${r.who.tags.map((t) => `<span class="chip ${r.who.tag_match.includes(t.name) ? "match" : ""}">${esc(t.name)}</span>`).join("")}</p>
      ${r.who.tag_match.length ? `<p class="status">Your confirmed taste appears among them: ${r.who.tag_match.map(esc).join(", ")}.</p>` : ""}`;
  });
  fill("#secWhere", r.where, () => {
    const cs = r.where.cells.filter((c) => c.lat != null && c.lon != null);
    if (!cs.length) return "<p class='status'>No cells.</p>";
    const la = cs.map((c) => c.lat), lo = cs.map((c) => c.lon);
    const [a0, a1, o0, o1] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    const X = (v) => 20 + ((v - o0) / ((o1 - o0) || 1)) * 360, Y = (v) => 180 - ((v - a0) / ((a1 - a0) || 1)) * 160;
    return `<svg viewBox="0 0 400 200" role="img" aria-label="Heatmap cells around ${esc(r.where.place)}"><rect width="400" height="200" rx="8" fill="var(--bg)"/>${cs.map((c, i) => `<circle cx="${X(c.lon).toFixed(1)}" cy="${Y(c.lat).toFixed(1)}" r="${(4 + 10 * (c.affinity || 0)).toFixed(1)}" fill="var(--bar)" fill-opacity="${(0.25 + 0.6 * (c.affinity || 0)).toFixed(2)}"><title>${esc(c.geohash)} affinity ${fmt(c.affinity)}</title></circle>${i < 3 ? `<text x="${Math.min(X(c.lon) + 8, 330).toFixed(1)}" y="${(Y(c.lat) - 8).toFixed(1)}" font-size="11" fill="var(--ink)">#${i + 1} ${esc(c.geohash)}</text>` : ""}`).join("")}</svg>
      <p class="status">${esc(r.where.place)}: ${cs.length} cells; bigger and darker = higher affinity.</p>`;
  });
  fill("#secRising", r.rising, () => r.rising.series.map((s) => {
    const v = s.points.map((p) => p.percentile), lo = Math.min(...v), hi = Math.max(...v);
    const pts = s.points.map((p, i) => `${(10 + (i / Math.max(1, s.points.length - 1)) * 380).toFixed(1)},${(50 - ((p.percentile - lo) / ((hi - lo) || 1)) * 40).toFixed(1)}`).join(" ");
    return `<div class="spark"><svg viewBox="0 0 400 56" role="img" aria-label="Trend of ${esc(s.name)}"><polyline points="${pts}" fill="none" stroke="${s.role === "rival" ? "var(--muted)" : "var(--bar)"}" stroke-width="2.5"/></svg>
      <p>${s.role === "rival" ? "rival " : ""}<b>${esc(s.name)}</b>: ${esc(s.direction)} (${s.change_points >= 0 ? "+" : ""}${fmt(s.change_points)} percentile points)</p></div>`;
  }).join(""));
  fill("#secFit", r.fit, () => `<ol class="rank">${r.fit.rows.map((x) => `<li class="${x.role}">${x.role === "rival" ? "rival: " : "your idea: "}<b>${esc(x.name)}</b> <span class="num">${fmt(x.affinity)}</span></li>`).join("")}</ol>
      <p class="status">Ranked for ${esc(r.fit.audience || "people")} in ${esc(r.fit.place)}. ${esc(r.fit.note)}</p>`);
  fill("#secRivals", r.rivals, () => r.rivals.items.length ? `<p>${r.rivals.items.map((i) => `<span class="chip">${esc(i.name)}</span>`).join("")}</p><p class="status">What Qloo's audience comparison returns for your idea's proxies (A) against the rivals (B).</p>` : "<p class='status'>Nothing returned.</p>");
  $("#hash").textContent = r.hash;
  $("#recordLine").textContent = r.record?.recorded ? `claim ${r.record.claim} (WARM line ${r.record.warm_seq}, COLD line ${r.record.cold_seq}; anchored on devnet with the next pre-order)` : `not recorded (${r.record?.why || "unknown"})`;
  $("#publishOut").textContent = "";
  $("#report").scrollIntoView({ behavior: "smooth" });
}
$("#publishGo").addEventListener("click", () => busy($("#publishGo"), "Listing...", async () => {
  const r = await api("/api/maker/publish", { hash: report.hash, title: $("#title").value });
  $("#publishOut").textContent = `Listed "${r.product.title}". Buyers will find it under "I want something".`;
  openLock(report.hash, r.product.title);
}));

// ---- buyer ----------------------------------------------------------------------------------------------------
$("#buyerForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  busy($("#buyerGo"), "Asking Qloo...", async () => {
    const targets = [...document.querySelectorAll("#targets input:checked")].map((x) => x.value);
    buyerS = await api("/api/buyer/start", { likes: $("#likes").value, vibes: $("#vibes").value, targets });
    $("#buyerOut").hidden = true; $("#buyerConfirm").hidden = false;
    renderQs($("#buyerQs"), buyerS, null); renderTrail(buyerS.trail);
  });
});
$("#buyerConfirmGo").addEventListener("click", () => busy($("#buyerConfirmGo"), "Asking Qloo...", async () => {
  const r = await api("/api/buyer/confirm", { session: buyerS.id, choices: choices($("#buyerQs"), buyerS) });
  $("#buyerConfirm").hidden = true; $("#buyerOut").hidden = false;
  const lab = $("#buyerLabel"); lab.textContent = `${r.label}. Results describe ${r.aggregate}.`; lab.classList.toggle("live", r.mode === "live");
  $("#products").innerHTML = r.products.length ? `<table class="tbl"><tr><th>Product (not built yet)</th><th>Type</th><th>Rank in type</th><th>Fit (Qloo affinity of its proxy)</th><th></th></tr>${r.products.map((p) => `<tr><td><b>${esc(p.title)}</b>${p.synthetic ? ' <span class="mockchip">MOCK report</span>' : ""}<br><span class="status">stands in Qloo as ${esc(p.proxy)}; maker's report: ${esc(p.lean)}</span></td><td>${esc(p.type)}</td><td>${esc(p.rank_in_type ?? "-")}</td><td class="num">${fmt(p.affinity)}</td><td><button type="button" data-h="${esc(p.report_hash)}" data-t="${esc(p.title)}">Pre-order</button></td></tr>`).join("")}</table><p class="status">${esc(r.why_rank_by_type)}</p>` : `<p class="status">${esc(r.note || "Nothing ranked.")}</p>`;
  $("#products").querySelectorAll("button[data-h]").forEach((b) => b.addEventListener("click", () => openLock(b.dataset.h, b.dataset.t)));
  $("#recs").innerHTML = r.recommendations.map((g) => `<p><b>${esc(g.target_type.replace("_", " "))}</b>: ${g.items.map((i) => `<span class="chip">${esc(i.name)} ${fmt(i.affinity)}</span>`).join("") || `<span class="status">${esc(g.status)}</span>`}</p>`).join("");
  renderTrail(r.trail);
}));

// ---- pre-orders (Knos devnet escrow) --------------------------------------------------------------------------
async function openLock(hash, title) {
  lockHash = hash; $("#lock").hidden = false; $("#lockTitle").textContent = title; $("#lockOut").innerHTML = ""; $("#poolOut").innerHTML = "";
  quote(); pool(); $("#lock").scrollIntoView({ behavior: "smooth" });
}
async function quote() {
  try {
    const q = await api(`/api/quote?units=${encodeURIComponent($("#units").value)}`);
    $("#quote").textContent = q.available ? `${fmt(q.at_lock.units, 3)} at lock (${q.at_lock.line}); ${fmt(q.at_release.units, 3)} at release (${q.at_release.line}, ${q.at_release.status}, paid by the ${q.at_release.payer}); ${fmt(q.on_graduation.units, 3)} Knos graduation fee (${q.on_graduation.status}, off chain). Demand report: ${q.demand_report.status}.` : q.why;
  } catch (e) { $("#quote").textContent = e.message; }
}
$("#units").addEventListener("change", quote);
async function pool() {
  try {
    const p = await api(`/api/pool?hash=${encodeURIComponent(lockHash)}`);
    $("#poolOut").innerHTML = `Pool for this report (read from devnet): <b>${p.buyers}</b> buyer(s), <b>${fmt(p.locked_units)}</b> test units locked in ${p.orders} order(s).`;
  } catch (e) { $("#poolOut").textContent = `Pool: ${e.message}`; }
}
function done(res, who) {
  const rec = res.record?.recorded ? `Knos Record: COLD line ${res.record.cold_seq}, WARM line ${res.record.warm_seq}.` : `Not recorded: ${esc(res.record?.why || "")}`;
  const anc = res.anchor?.anchored ? ` Anchored on devnet: <a href="${esc(res.anchor.explorer)}" target="_blank" rel="noopener">${esc(res.anchor.tx)}</a>.` : res.anchor ? ` Anchor: ${esc(res.anchor.why)}` : "";
  $("#lockOut").innerHTML = `Locked ${esc(res.amount_units ?? "")} test units as ${esc(who)}. Transaction: <a href="${esc(res.explorer)}" target="_blank" rel="noopener">${esc(res.signature)}</a>${res.order ? `<br>Escrow order: ${esc(res.order)}` : ""}<br>${rec}${anc}`;
  pool();
}
$("#demoBuy").addEventListener("click", () => busy($("#demoBuy"), "Sending to Solana devnet...", async () => {
  done(await api("/api/preorder/demo", { hash: lockHash, units: Number($("#units").value) }), "the demo buyer (devnet test wallet)");
}));
function loadWeb3() {
  return new Promise((ok, no) => {
    if (window.solanaWeb3) return ok(window.solanaWeb3);
    const s = document.createElement("script");
    s.src = "https://unpkg.com/@solana/web3.js@1.98.0/lib/index.iife.min.js";
    s.onload = () => ok(window.solanaWeb3); s.onerror = () => no(new Error("could not load @solana/web3.js"));
    document.head.appendChild(s);
  });
}
$("#walletBuy").addEventListener("click", () => busy($("#walletBuy"), "Waiting for the wallet...", async () => {
  const provider = window.phantom?.solana || window.solana;
  if (!provider) throw new Error("No Solana wallet found. Install Phantom and switch it to devnet, or use the demo buyer.");
  const web3 = await loadWeb3();
  const owner = (await provider.connect()).publicKey.toString();
  await api("/api/preorder/faucet", { owner }).catch(() => {});
  const units = Number($("#units").value);
  const t = await api("/api/preorder/tx", { hash: lockHash, owner, units });
  const tx = web3.Transaction.from(Uint8Array.from(atob(t.transaction), (c) => c.charCodeAt(0)));
  const signed = await provider.signTransaction(tx);
  const raw = btoa(String.fromCharCode(...signed.serialize()));
  done(await api("/api/preorder/submit", { transaction: raw, owner, hash: lockHash, units, order: t.order }), `your wallet ${owner}`);
}));

loadStatus();
