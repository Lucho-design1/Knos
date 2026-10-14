"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 2) => (typeof n === "number" ? n.toFixed(d) : "n/a");
let current = null;

const EXAMPLES = [
  { idea: "A late-night oat-milk coffee bar for students in London", rivals: "", place: "London" },
  { idea: "A true-crime podcast for women about unsolved art heists", rivals: "", place: "" },
  { idea: "A vegan Nigerian street-food truck for young professionals in New York", rivals: "", place: "New York" },
  { idea: "Recycled-plastic trail running shoes for parents", rivals: "Allbirds, Salomon", place: "" },
];

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
function showErr(msg) { const e = $("#err"); e.textContent = msg; e.hidden = !msg; }

async function status() {
  try {
    const s = await api("/api/status");
    const b = $("#modeBadge");
    b.textContent = s.label;
    b.classList.toggle("live", s.mode === "live");
    $("#framing").textContent = s.framing;
    if (!s.escrow) { $("#demoBuy").disabled = true; $("#walletBuy").disabled = true; $("#lockOut").textContent = "Escrow unavailable on this server (the knos package is not installed)."; }
    else if (!s.demo_wallet) { $("#demoBuy").disabled = true; $("#walletBuy").disabled = true; $("#lockOut").textContent = "Escrow unavailable: this server has no devnet test wallet configured."; }
  } catch (e) { $("#modeBadge").textContent = "server unreachable"; }
}

function sectionStatus(sec) {
  const words = { mock: "", live: "", "not served": "Not served by this Qloo key.", failed: "The Qloo call failed.", "no data": "Qloo answered without data for this.", "no input": sec.note || "Not enough input." };
  return `<p class="status">${esc(words[sec.status] ?? sec.status)}${sec.note && sec.status !== "no input" ? " " + esc(sec.note) : ""}</p>`;
}
function bar(label, v, min, max, cls = "") {
  const span = max - min || 1, zero = ((0 - min) / span) * 100, pos = ((v - min) / span) * 100;
  const left = Math.min(zero, pos), width = Math.abs(pos - zero);
  return `<div class="barrow"><span class="lbl" title="${esc(label)}">${esc(label)}</span><span class="track"><span class="fill ${v < 0 ? "neg" : ""} ${cls}" style="left:${left}%;width:${Math.max(width, 1)}%"></span></span><span class="num">${fmt(v)}</span></div>`;
}
function fill(id, sec, html) {
  const el = document.querySelector(id);
  el.querySelector(".body").innerHTML = sec.status === "ok" ? html() : sectionStatus(sec);
  el.querySelector(".src").textContent = sec.source ? `Source: ${sec.source}` : "";
}

function render(r) {
  current = r;
  $("#report").hidden = false;
  const lw = $("#leanWord");
  lw.textContent = r.lean.word;
  lw.className = "lean-word " + (r.lean.word === "leans wanted" ? "leans" : r.lean.word === "weak" ? "weak" : r.lean.word === "mixed" ? "mixed" : "");
  $("#leanWhy").innerHTML = r.lean.why.map((w) => `<li>${esc(w)}</li>`).join("") || "<li>Not enough sections with data.</li>";
  const lab = $("#reportLabel"); lab.textContent = `${r.label}. ${r.framing}`; lab.classList.toggle("live", r.mode === "live");
  const p = r.plan, inp = r.inputs;
  $("#plan").innerHTML = `Planner: ${esc(p.planner)} | category ${esc(p.category)} | proxies ${inp.proxies.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("") || "none"}
    rivals ${inp.rivals.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("") || "none"} tags ${inp.tags.map((t) => `<span class="chip">${esc(t.name)}</span>`).join("") || "none"}
    ${p.audience.age.length ? "| audience ages " + p.audience.age.map(esc).join(", ") : ""} ${p.audience.gender ? "| " + esc(p.audience.gender) : ""} ${p.location ? "| place " + esc(p.location) : ""}`;

  fill("#secWho", r.who, () => {
    const segs = r.who.segments, m = Math.max(0.5, ...segs.map((s) => Math.abs(s.score)));
    const g = Object.entries(r.who.gender || {}).map(([k, v]) => bar(k, v, -m, m)).join("");
    return `<div class="bars">${segs.map((s) => bar(s.label, s.score, -m, m)).join("")}${g}</div><p class="status">Above 0: leans in more than average; below 0: less (Qloo demographic affinity).</p>`;
  });
  fill("#secWhere", r.where, () => {
    const cs = r.where.cells.filter((c) => c.lat != null && c.lon != null);
    if (!cs.length) return "<p class='status'>No cells.</p>";
    const la = cs.map((c) => c.lat), lo = cs.map((c) => c.lon);
    const [a0, a1, o0, o1] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    const X = (v) => 20 + ((v - o0) / ((o1 - o0) || 1)) * 360, Y = (v) => 180 - ((v - a0) / ((a1 - a0) || 1)) * 160;
    const dots = cs.map((c, i) => `<circle cx="${X(c.lon).toFixed(1)}" cy="${Y(c.lat).toFixed(1)}" r="${(4 + 10 * (c.affinity || 0)).toFixed(1)}" fill="var(--bar)" fill-opacity="${(0.25 + 0.6 * (c.affinity || 0)).toFixed(2)}"><title>${esc(c.geohash)} affinity ${fmt(c.affinity)}</title></circle>${i < 3 ? `<text x="${(X(c.lon) + 8).toFixed(1)}" y="${(Y(c.lat) - 8).toFixed(1)}" font-size="11" fill="var(--ink)">#${i + 1} ${esc(c.geohash)}</text>` : ""}`).join("");
    return `<svg viewBox="0 0 400 200" role="img" aria-label="Heatmap cells around ${esc(r.where.location)}"><rect x="0" y="0" width="400" height="200" rx="8" fill="var(--bg)"/>${dots}</svg>
      <p class="status">${esc(r.where.location)}: ${cs.length} cells, bigger and darker = higher affinity. Top cell geohash ${esc(cs[0].geohash)} (affinity ${fmt(cs[0].affinity)}).</p>`;
  });
  fill("#secStrength", r.strength, () => {
    const rows = r.strength.rows, m = Math.max(0.01, ...rows.map((x) => x.affinity || 0));
    return `<div class="bars">${rows.map((x) => x.affinity == null ? `<div class="barrow"><span class="lbl">${esc(x.name)}</span><span class="status">no score</span><span></span></div>` : bar(`${x.role === "rival" ? "rival: " : "idea: "}${x.name}`, x.affinity, 0, m, x.role === "rival" ? "rival" : "")).join("")}</div>
      ${r.strength.note ? `<p class="status">${esc(r.strength.note)}</p>` : ""}<p class="status">Qloo affinity of each for the idea's taste tags and audience.</p>`;
  });
  fill("#secRising", r.rising, () => {
    const s = r.rising.series, v = s.map((x) => x.percentile), lo = Math.min(...v), hi = Math.max(...v);
    const pts = s.map((x, i) => `${(10 + (i / Math.max(1, s.length - 1)) * 380).toFixed(1)},${(110 - ((x.percentile - lo) / ((hi - lo) || 1)) * 90).toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 400 120" role="img" aria-label="Trend line"><polyline points="${pts}" fill="none" stroke="var(--bar)" stroke-width="2.5"/></svg>
      <p><b>${esc(r.rising.direction)}</b>: ${r.rising.change_points >= 0 ? "+" : ""}${fmt(r.rising.change_points)} percentile points for ${esc(r.rising.entity)} (${esc(s[0].date)} to ${esc(s[s.length - 1].date)}).</p>`;
  });
  fill("#secWhy", r.why, () => `<table class="tbl"><tr><th>This audience also likes</th><th>Affinity</th><th>Driven by (Qloo explainability)</th></tr>${r.why.neighbours.map((n) => `<tr><td>${esc(n.name)}</td><td class="num">${fmt(n.affinity)}</td><td>${n.drivers.map((d) => `<span class="chip">${esc(d.input)} ${fmt(d.score)}</span>`).join("") || "<span class='status'>none returned</span>"}</td></tr>`).join("")}</table>${r.why.warning ? `<p class="status">${esc(r.why.warning)}</p>` : ""}`);
  fill("#secCompare", r.compare, () => r.compare.items.length ? `<ol>${r.compare.items.map((i) => `<li>${esc(i.name)}</li>`).join("")}</ol><p class="status">What Qloo's compare returns for the idea's proxies (A) against the rivals (B).</p>` : "<p class='status'>Nothing returned.</p>");
  $("#secCalls .body").innerHTML = `<table class="tbl"><tr><th>Endpoint</th><th>Result</th></tr>${r.calls.map((c) => `<tr><td>${esc(c.endpoint)}</td><td>${esc(c.status)}${c.http ? " (HTTP " + esc(c.http) + ")" : ""}</td></tr>`).join("")}</table>`;
  $("#hash").textContent = r.hash;
  $("#lockOut").innerHTML = ""; $("#poolOut").innerHTML = "";
  $("#report").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function pool() {
  try {
    const p = await api(`/api/pool?hash=${encodeURIComponent(current.hash)}`);
    $("#poolOut").innerHTML = `Pool for this report (read from devnet): <b>${p.buyers}</b> buyer(s), <b>${fmt(p.locked_units)}</b> test units locked in ${p.orders} order(s).`;
  } catch (e) { $("#poolOut").textContent = `Pool: ${e.message}`; }
}
function done(res, who) {
  $("#lockOut").innerHTML = `Locked ${esc(res.amount_units ?? "")} test units (+ ${esc(res.fee_units ?? "")} fee) as ${esc(who)}. Transaction: <a href="${esc(res.explorer)}" target="_blank" rel="noopener">${esc(res.signature)}</a>${res.order_explorer ? `<br>Escrow order: <a href="${esc(res.order_explorer)}" target="_blank" rel="noopener">${esc(res.order)}</a>` : res.order ? `<br>Escrow order: ${esc(res.order)}` : ""}`;
  pool();
}

$("#demoBuy").addEventListener("click", async () => {
  if (!current) return;
  const b = $("#demoBuy"); b.disabled = true; $("#lockOut").textContent = "Sending to Solana devnet...";
  try { done(await api("/api/preorder/demo", { hash: current.hash, units: Number($("#units").value) }), "the demo buyer (devnet test wallet)"); }
  catch (e) { $("#lockOut").textContent = e.message; }
  b.disabled = false;
});

function loadWeb3() {
  return new Promise((ok, no) => {
    if (window.solanaWeb3) return ok(window.solanaWeb3);
    const s = document.createElement("script");
    s.src = "https://unpkg.com/@solana/web3.js@1.98.0/lib/index.iife.min.js";
    s.onload = () => ok(window.solanaWeb3); s.onerror = () => no(new Error("could not load @solana/web3.js"));
    document.head.appendChild(s);
  });
}
$("#walletBuy").addEventListener("click", async () => {
  if (!current) return;
  const provider = window.phantom?.solana || window.solana;
  if (!provider) { $("#lockOut").innerHTML = 'No Solana wallet found. Install Phantom, switch it to devnet (Settings, Developer settings, Testnet mode), or use the demo buyer.'; return; }
  const b = $("#walletBuy"); b.disabled = true;
  try {
    const web3 = await loadWeb3();
    const owner = (await provider.connect()).publicKey.toString();
    $("#lockOut").textContent = "Sending test units and a little devnet SOL to your wallet...";
    await api("/api/preorder/faucet", { owner }).catch((e) => { $("#lockOut").textContent = `Faucet: ${e.message} (continuing)`; });
    const units = Number($("#units").value);
    const t = await api("/api/preorder/tx", { hash: current.hash, owner, units });
    $("#lockOut").textContent = "Approve the pre-order in your wallet...";
    const tx = web3.Transaction.from(Uint8Array.from(atob(t.transaction), (c) => c.charCodeAt(0)));
    const signed = await provider.signTransaction(tx);
    const raw = btoa(String.fromCharCode(...signed.serialize()));
    const res = await api("/api/preorder/submit", { transaction: raw, owner });
    done({ ...res, order: t.order, amount_units: t.amount_units, fee_units: t.fee_units }, `your wallet ${owner}`);
  } catch (e) { $("#lockOut").textContent = e.message || String(e); }
  b.disabled = false;
});

$("#ideaForm").addEventListener("submit", async (ev) => {
  ev.preventDefault(); showErr("");
  const go = $("#go"); go.disabled = true; go.textContent = "Asking Qloo...";
  try { render(await api("/api/report", { idea: $("#idea").value, rivals: $("#rivals").value, location: $("#place").value })); }
  catch (e) { showErr(e.message); }
  go.disabled = false; go.textContent = "Build the Wanted Report";
});
$("#examples").innerHTML = EXAMPLES.map((e, i) => `<button type="button" data-i="${i}">${esc(e.idea.slice(0, 48))}${e.idea.length > 48 ? "..." : ""}</button>`).join("");
$("#examples").addEventListener("click", (ev) => {
  const i = ev.target?.dataset?.i; if (i == null) return;
  const e = EXAMPLES[i]; $("#idea").value = e.idea; $("#rivals").value = e.rivals; $("#place").value = e.place;
});
status();
