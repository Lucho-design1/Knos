// Knos projects (tranches, attempts, AMC, pools, referrals) and teams (SSO, Squads, ERP, sandbox). Uses app.js's helpers.
"use strict";
(function () {
  const I = window.KNOS_I18N;
  if (I) {
    const nav = { en: ["Projects", "Teams"], fr: ["Projets", "Équipes"], es: ["Proyectos", "Equipos"], pt: ["Projetos", "Equipes"],
      ar: ["المشاريع", "الفرق"], hi: ["परियोजनाएँ", "टीमें"], zh: ["项目", "团队"] };
    for (const [l, [p, tm]] of Object.entries(nav)) if (I[l]) { I[l].nav_projects = p; I[l].nav_teams = tm; }
  }
  try { const r = new URLSearchParams(location.search).get("ref"); if (r && /^[0-9a-f]{12}$/.test(r)) localStorage.setItem("knos.ref", r); } catch (e) { /* private */ }
})();

const V = { templates: null, project: null };
const ref = () => { try { return localStorage.getItem("knos.ref") || undefined; } catch (e) { return undefined; } };
const STATUS = { open: "Open", funded: "Funded", claimed: "In progress", released: "Released", reopened: "Reopened" };

async function walletSign(b64) {
  const w = window.phantom && window.phantom.solana || window.solflare || window.solana;
  if (!w) throw new Error("Connect a Solana wallet (Phantom, Solflare) set to devnet to sign this.");
  const web3 = await loadWeb3();
  const tx = web3.Transaction.from(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)));
  const signed = await w.signTransaction(tx);
  return new web3.Connection("https://api.devnet.solana.com", "confirmed").sendRawTransaction(signed.serialize());
}
async function walletAccount() {
  const w = window.phantom && window.phantom.solana || window.solflare || window.solana;
  if (!w) throw new Error("Connect a Solana wallet (Phantom, Solflare) set to devnet.");
  await w.connect(); return w.publicKey.toString();
}
async function settle(confirmPath, idKey, id, sig) {
  for (let i = 0; i < 10; i++) {
    try { return await api(confirmPath, { [idKey]: id, signature: sig }); } catch (e) { await new Promise((r) => setTimeout(r, 2500)); }
  }
  throw new Error("Sent " + sig.slice(0, 10) + "… but devnet has not shown it yet; refresh in a minute.");
}

// ---- projects --------------------------------------------------------------------------------------------------------
async function loadProjects() {
  const h = location.hash.match(/^#projects=([0-9a-f]{16})/);
  if (!V.templates) V.templates = await api("/api/templates").catch(() => null);
  renderNewForm();
  if (h) return loadProject(h[1]);
  $("projDetail").hidden = true; $("projHome").hidden = false;
  const got = await api("/api/projects").catch((e) => { err(e); return { projects: [] }; });
  const box = $("projList");
  box.innerHTML = got.projects.length ? got.projects.map((p) => {
    const locked = p.milestones.reduce((a, m) => a + m.locked_units, 0);
    const done = p.milestones.filter((m) => m.status === "released").length;
    return `<li class="card pcard"><a href="#projects=${p.id}"><strong>${esc(p.title)}</strong></a>
      <p class="small muted">${esc(p.template_name)}${p.regulatory.length ? " · regulated (" + esc(p.regulatory.join(", ").toUpperCase()) + ")" : ""}${p.sandbox ? " · one-day sandbox" : ""}</p>
      <p class="small">${done} of ${p.milestones.length} milestones released · ${locked} test units in escrow</p></li>`;
  }).join("") : `<li class="muted">No projects yet. Open the first one above.</li>`;
  renderPool(got.projects);
}
function renderNewForm() {
  const T = V.templates; if (!T || $("tplPick").dataset.done) return;
  $("tplPick").dataset.done = "1";
  $("tplPick").innerHTML = T.templates.map((t, i) => `<label class="opt"><input type="radio" name="tpl" value="${t.key}" ${i === 0 ? "checked" : ""}>
    <span><strong>${esc(t.name)}</strong><br><span class="small muted">${esc(t.for)} · ${t.milestones.length} milestones</span></span></label>`).join("");
  $("regPick").innerHTML = T.regulatory.sets.map((s) => `<label class="opt"><input type="checkbox" name="reg" value="${s.key}">
    <span>${esc(s.name)} <span class="small muted">(${s.milestones.length} milestones)</span></span></label>`).join("") +
    `<p class="small muted">${esc(T.regulatory.attribution)} <a href="${esc(T.regulatory.source)}" rel="noopener">Source</a>. ${esc(T.regulatory.licence)}</p>`;
}
async function openProject(sandbox) {
  if (!session) { $("signin").hidden = false; throw new Error("Sign in first: a project has an owner."); }
  const tpl = (document.querySelector("input[name=tpl]:checked") || {}).value;
  const regs = [...document.querySelectorAll("input[name=reg]:checked")].map((x) => x.value);
  const p = sandbox ? await api("/api/sandbox", { template: tpl, title: $("pTitle").value.trim() || "One-day sandbox project", team: $("pTeam").value.trim() })
    : await api("/api/project", { template: tpl, title: $("pTitle").value.trim(), regulatory: regs, team: $("pTeam").value.trim() });
  location.hash = "#projects=" + p.id;
}
function dur(s) { return s >= 86400 ? Math.round(s / 86400) + " days" : s >= 3600 ? Math.round(s / 3600) + " h" : Math.round(s / 60) + " min"; }
async function loadProject(id) {
  $("projHome").hidden = true; $("projDetail").hidden = false;
  const p = V.project = await api("/api/project?id=" + id);
  $("projHead").innerHTML = `<p class="small"><a href="#projects">← All projects</a></p><h2>${esc(p.title)}</h2>
    <p class="small muted">${esc(p.template_name)} · opened by ${esc(p.owner_label || "a signed-in user")}${p.team ? " for " + esc(p.team) : ""} · ${esc(p.money)}</p>
    <p class="small">Each milestone has its own escrow. It pays on a result plus an independent check. A missed deadline refunds and reopens it.</p>
    <div class="row"><button type="button" class="quiet" id="refBtn">Get my referral link</button>
      <a class="button ghost small" href="/api/company/export?project=${p.id}&format=journal">Ledger CSV</a></div><p id="refOut" class="small"></p>`;
  $("refBtn").onclick = () => busy($("refBtn"), "Making link", async () => {
    if (!session) { $("signin").hidden = false; throw new Error("Sign in first."); }
    const r = await api("/api/referral", { passkey: true, target: "p=" + p.id });
    $("refOut").innerHTML = `Share <span class="mono">${esc(location.origin + r.link)}</span>: ${esc(r.rule)} (${r.share_bps / 100}%).`;
  });
  $("msList").innerHTML = p.milestones.map((m, i) => msCard(p, m, i)).join("");
  p.milestones.forEach((m, i) => wire(p, m, i));
}
// The code referee's four proofs for one order (knos_wanted.referee.trust): each one checks without Knos.
function trustLine(t) {
  if (!t) return "";
  const a = t.attestation || {};
  const parts = [
    t.run ? `<a href="${esc(t.run)}" rel="noopener">referee run</a>` : `<span class="muted">referee run: waiting for GitHub Actions</span>`,
    t.oidc_verify ? `<a href="${X(t.oidc_verify[0])}" rel="noopener">knos_oidc verification</a>` : `<span class="muted">knos_oidc verification: not yet</span>`,
    a.ok ? `<a href="${esc(a.url || a.rekor || "#")}" rel="noopener">Sigstore attestation</a>${a.rekor && a.url ? ` (<a href="${esc(a.rekor)}" rel="noopener">Rekor</a>)` : ""}` : `<span class="muted">attestation: ${esc(a.why || "not yet")}</span>`,
    t.release ? `<a href="${X(t.release)}" rel="noopener">FROST release</a>` : `<span class="muted">FROST release: ${esc(t.state || "waiting")} (2 of 3 hosts)</span>`,
  ];
  return `<br><span class="small">Code referee: ${parts.join(" · ")}</span>`;
}
function msCard(p, m, i) {
  const live = m.attempts.filter((a) => ["working", "result posted", "checked"].includes(a.status));
  const reg = m.kind === "regulatory" ? `<p class="small"><span class="tag">Regulatory · ${esc(m.standard)}</span> <a href="${esc(m.template)}" rel="noopener">OpenRegulatory template</a></p>` : "";
  const cap = (m.route && m.route.capacity || []).map((c) => `<li>${esc(c.name)}${c.quote && c.quote.price != null ? ` — quote ${c.quote.price} ${esc(c.quote.currency)}, ${c.quote.turnaround_days} days <span class="small muted">(${c.quote.fixture ? "fixture quote, labelled" : "live"})</span>` : ""}${c.manual ? ` — <a href="${esc(c.manual)}" rel="noopener">order on their site</a>` : ""}</li>`).join("");
  const orders = m.orders.map((o) => `<li class="small"><a href="${o.explorer}" rel="noopener">${short(o.order)}</a> ${o.units} units · ${esc(o.kind)}${o.grant ? " (" + esc(o.grant.agency) + " " + esc(o.grant.id) + ")" : ""} · <strong>${esc(o.status)}</strong>${o.signatures && o.signatures.refund ? ` · <a href="${X(o.signatures.refund)}" rel="noopener">refund</a>` : ""}${o.signatures && (o.signatures.referee_2_pass || o.signatures.referee_group_pass) ? ` · <a href="${X(o.signatures.referee_2_pass || o.signatures.referee_group_pass)}" rel="noopener">release</a>` : ""}${trustLine(o.trust)}</li>`).join("");
  const atts = m.attempts.map((a) => `<li class="small">${esc(a.maker)} · <strong>${esc(a.status)}</strong>${a.result ? ` · <a href="${esc(a.result.url)}" rel="noopener nofollow">result</a>` : ""}${a.check ? ` · <a href="${esc(a.check.url)}" rel="noopener nofollow">check</a> by ${esc(a.check.by)}` : ""}${a.result ? ` · <a href="/api/attest?project=${p.id}&milestone=${m.key}&attempt=${a.id}" rel="noopener">in-toto attestation</a>` : ""} <span class="mono muted">${esc(a.id)}</span></li>`).join("");
  return `<li class="card ms" id="ms${i}"><div class="row spread"><h3>${esc(m.name)}</h3><span class="chip st-${esc(m.status)}">${esc(STATUS[m.status] || m.status)}</span></div>
    ${reg}<p class="small muted">Deadline ${dur(m.deadline_s)} after funding · ${m.locked_units} test units in escrow · ${m.amc_units} committed (AMC)${m.excluded_makers ? ` · ${m.excluded_makers} maker(s) missed it` : ""}</p>
    ${orders ? `<ul class="list">${orders}</ul>` : ""}${atts ? `<p class="small"><strong>Attempts</strong> (up to 3 in parallel)</p><ul class="list">${atts}</ul>` : ""}
    ${cap ? `<details><summary class="small">Where this work can be bought</summary><ul class="list small">${cap}</ul><p class="small muted">${esc(m.route.rule)}</p></details>` : ""}
    ${m.game ? `<p class="small">Code-scored: attempts also run as a <a href="#contribute">knos.game round</a>.</p>` : ""}
    ${m.status === "released" ? "" : `<details><summary>Fund or commit</summary>
      <label for="u${i}">Test units</label><input id="u${i}" type="number" min="5" max="1000" value="10" inputmode="numeric">
      <label for="k${i}">As</label><select id="k${i}" class="field"><option value="funder">a funder (escrow now)</option><option value="grant">a grant (escrow now, labelled)</option><option value="amc">a buyer commitment (pays only when it verifies)</option></select>
      <div id="g${i}" hidden><label for="ga${i}">Grant agency</label><input id="ga${i}" maxlength="120"><label for="gi${i}">Grant id</label><input id="gi${i}" maxlength="120"></div>
      <button type="button" id="f${i}">Approve with my passkey</button><p class="small muted">Test units. Refunds go back to your passkey wallet.</p></details>
    <details><summary>Make it</summary>
      <button type="button" class="ghost" id="c${i}">Attempt this milestone</button>
      <label for="e${i}">Evidence page (public https, contains the claim id${m.orders[0] ? ": " + esc(m.orders[0].claim_id) : ""})</label><input id="e${i}" inputmode="url" maxlength="2000" placeholder="https://">
      <label for="a${i}">Attempt id</label><input id="a${i}" maxlength="12" value="${esc((live[0] || {}).id || "")}">
      <div class="row"><button type="button" class="ghost" id="r${i}">Post my result</button><button type="button" class="ghost" id="x${i}">Post an independent check</button></div></details>`}
    <p id="o${i}" class="small" aria-live="polite"></p></li>`;
}
function wire(p, m, i) {
  const out = (h) => { $("o" + i).innerHTML = h; };
  const k = $("k" + i); if (!k) return;
  k.onchange = () => { $("g" + i).hidden = k.value !== "grant"; };
  $("f" + i).onclick = () => busy($("f" + i), "Approve on your passkey", async () => {
    if (!session) { $("signin").hidden = false; throw new Error("Sign in with your passkey first."); }
    const units = parseInt($("u" + i).value, 10);
    if (k.value === "amc") {
      const a = await KnosPasskey.approve(await api("/api/project/amc", { passkey: true, project: p.id, milestone: m.key, units }), api);
      const sig = (a.signatures || {}).approve;
      out(`Committed ${esc(a.units)} test units: paid to the maker only when it verifies.${sig ? ` <a href="${X(sig)}" rel="noopener">Allowance on devnet</a>.` : ""}`);
    } else {
      const grant = k.value === "grant" ? { agency: $("ga" + i).value, id: $("gi" + i).value } : undefined;
      const f = await KnosPasskey.approve(await api("/api/project/fund", { passkey: true, project: p.id, milestone: m.key, units, kind: k.value, grant, ref: ref() }), api);
      const sig = (f.signatures || {}).lock;
      out(`Locked in escrow.${sig ? ` <a href="${X(sig)}" rel="noopener">On devnet</a>.` : ""}`);
    }
    setTimeout(() => loadProject(p.id), 1500);
  });
  $("c" + i).onclick = () => busy($("c" + i), "Claiming", async () => {
    if (!session) { $("signin").hidden = false; throw new Error("Sign in first."); }
    const a = await api("/api/project/claim", { passkey: true, project: p.id, milestone: m.key });
    $("a" + i).value = a.id; out(`Attempt ${esc(a.id)} is yours; you are paid to your passkey wallet.`);
  });
  for (const [b, role] of [["r", "result"], ["x", "check"]]) $(b + i).onclick = () => busy($(b + i), "Fetching the page", async () => {
    if (!session) { $("signin").hidden = false; throw new Error("Sign in first."); }
    const r = await api("/api/project/post", { project: p.id, milestone: m.key, attempt: $("a" + i).value.trim(), url: $("e" + i).value.trim(), role });
    out(r.released ? (r.milestone === "signing" ? "Verified: 2 of 3 referee hosts are checking the review and signing the release." : `Released: ${r.released.map((x) => esc(x.status)).join(", ")}.`) : `Posted. Next: ${esc(r.next)}.`);
    setTimeout(() => loadProject(p.id), 1500);
  });
}
function renderPool(projects) {
  const open = []; projects.forEach((p) => p.milestones.forEach((m) => { if (m.status !== "released") open.push({ p, m }); }));
  $("poolBox").hidden = open.length < 2;
  $("poolPick").innerHTML = open.slice(0, 24).map((x, i) => `<label class="opt"><input type="checkbox" name="pool" value="${i}" data-p="${x.p.id}" data-m="${x.m.key}">
    <span>${esc(x.m.name)} <span class="small muted">— ${esc(x.p.title)}</span></span></label>`).join("");
}
async function pool() {
  if (!session) { $("signin").hidden = false; throw new Error("Sign in with your passkey first."); }
  const picks = [...document.querySelectorAll("input[name=pool]:checked")].map((x) => ({ project: x.dataset.p, milestone: x.dataset.m }));
  if (picks.length < 2 || picks.length > 8) throw new Error("Pick 2 to 8 milestones.");
  const total = parseInt($("poolUnits").value, 10), each = Math.floor(total / picks.length);
  if (each < 5) throw new Error(`At least 5 test units per milestone (${5 * picks.length}).`);
  const r = await api("/api/project/pool", { passkey: true });
  const sigs = [];
  for (const x of picks) {          // one escrow per milestone, one passkey approval each
    const f = await KnosPasskey.approve(await api("/api/project/fund", { passkey: true, ...x, units: each, kind: "pool", pool: r.pool, ref: ref() }), api);
    sigs.push((f.signatures || {}).lock || f.order);
  }
  $("poolOut").innerHTML = `Pooled ${each * sigs.length} test units over ${sigs.length} milestones: ` + sigs.map((s) => `<a href="${X(s)}" rel="noopener">${short(s)}</a>`).join(" ");
}

// ---- teams -----------------------------------------------------------------------------------------------------------
async function loadTeams() {
  const c = await api("/api/sso/config").catch(() => ({ enabled: false }));
  $("ssoNote").textContent = c.enabled ? `Through SAML Jackson. Test IdP: ${c.test_idp}.` : "Single sign-on is not switched on on this server.";
  $("ssoBtn").disabled = !c.enabled; if (!$("ssoTenant").value) $("ssoTenant").value = c.test_tenant || "knos-test";
  const tt = c.test_tenants || [];
  $("ssoTenants").innerHTML = tt.map((x) => `<option value="${esc(x.tenant)}">`).join("");
  $("ssoTest").innerHTML = c.enabled ? tt.map((x) => `<li class="small">Test tenant <button type="button" class="quiet" data-tenant="${esc(x.tenant)}">${esc(x.tenant)}</button> · ${esc(x.idp)}</li>`).join("") : "";
  for (const b of $("ssoTest").querySelectorAll("button[data-tenant]")) b.onclick = () => { $("ssoTenant").value = b.dataset.tenant; $("ssoBtn").click(); };
  const got = await api("/api/companies").catch(() => ({ companies: [] }));
  $("coList").innerHTML = got.companies.map((x) => `<li class="small"><strong>${esc(x.name)}</strong> · ${x.threshold} of ${x.members.length} · ${esc(x.status)} · <a href="${X(x.multisig, "address")}" rel="noopener">multisig</a> · vault <span class="mono">${short(x.vault)}</span></li>`).join("") || `<li class="muted small">No companies yet.</li>`;
  const pr = await api("/api/projects").catch(() => ({ projects: [] }));
  $("erpProject").innerHTML = pr.projects.map((p) => `<option value="${p.id}">${esc(p.title)}</option>`).join("");
  $("tplCount").textContent = V.templates ? V.templates.templates.length : 5;
  const pf = await api("/api/proofs").catch(() => ({ proofs: [] }));
  const li = (x) => `<li class="small"><details><summary><strong>${esc(x.title)}</strong> · ${esc(x.result)} · ${esc(x.where)} · ${esc((x.ran_at || "").slice(0, 10))}</summary>
    <p>${esc(x.summary)}</p>${(x.run_yourself || []).length ? `<p class="muted">Run it yourself:</p><pre class="mono">${esc(x.run_yourself.join("
"))}</pre>` : ""}</details></li>`;
  $("proofList").innerHTML = (pf.proofs || []).map(li).join("") || `<li class="muted small">No recorded proofs in this build.</li>`;
  $("erpProofs").innerHTML = (pf.proofs || []).filter((x) => x.key.startsWith("erp_")).map(li).join("") || `<li class="muted small">None recorded.</li>`;
}
async function companyCreate() {
  const creator = await walletAccount();
  const members = [creator, ...$("coMembers").value.split(/[\s,]+/).map((s) => s.trim()).filter((s) => s && s !== creator)];
  const r = await api("/api/company/multisig", { name: $("coName").value, members, threshold: parseInt($("coThreshold").value, 10), creator });
  const sig = await walletSign(r.transaction); const c = await settle("/api/company/confirm", "company", r.company, sig);
  $("coOut").innerHTML = `Created: <a href="${c.explorer}" rel="noopener">multisig ${short(c.multisig)}</a>, vault <span class="mono">${esc(c.vault)}</span>. Knos holds no key in it.`;
  loadTeams();
}

window.KNOS_VIEW = function (view) {
  if (view === "projects") loadProjects();
  if (view === "teams") loadTeams();
};
document.addEventListener("DOMContentLoaded", () => {
  $("pNew").onclick = () => busy($("pNew"), "Opening", () => openProject(false));
  $("pSandbox").onclick = () => busy($("pSandbox"), "Opening", () => openProject(true));
  $("sbBtn").onclick = () => { location.hash = "#projects"; setTimeout(() => $("pSandbox").click(), 50); };
  $("poolBtn").onclick = () => busy($("poolBtn"), "Approve on your passkey", pool);
  $("ssoBtn").onclick = () => { location.href = "/auth/sso?tenant=" + encodeURIComponent($("ssoTenant").value.trim()); };
  $("coBtn").onclick = () => busy($("coBtn"), "Waiting for your wallet", companyCreate);
  const exp = (fmt) => () => { const p = $("erpProject").value; if (p) location.href = `/api/company/export?project=${p}&format=${fmt}`; };
  for (const f of ["journal", "xero", "quickbooks", "netsuite"]) $("erp_" + f).onclick = exp(f);
});
