// The one box of both front doors (web/brand/hero.html): a DOI, an arXiv id or an idea in, Qloo's demand verdict out,
// drawn as one card: open or refuse, who, where (on a map), and the price tier, each part linked to the Qloo call it
// came from (the app's /trace.html: the redacted request, the result excerpt and the limit). A paper goes through the
// crossing (POST /api/cross: the paper read, its product named, then the check); an idea straight to the check
// (POST /api/check). Nothing here is estimated: an empty part says what Qloo did not answer.
(() => {
  const root = document.getElementById("k-hero");
  if (!root || root.dataset.ready) return;
  root.dataset.ready = "1";
  // the app's address: the front door's page names no other host (it says "@app"); the app's own page uses its own
  const API = root.dataset.api === "@app" ? "https://knos.onrender.com" : root.dataset.api || "", APP = root.dataset.app || "/";
  const form = document.getElementById("k-ask"), q = document.getElementById("k-q"), go = document.getElementById("k-go"), slot = document.getElementById("k-card");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const DOI = /^(?:doi:\s*|https?:\/\/(?:dx\.)?doi\.org\/)?(10\.\d{4,9}\/\S+)$/i;
  const ARXIV = /^(?:arxiv:\s*|https?:\/\/arxiv\.org\/(?:abs|pdf)\/)?(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?$/i;
  const paper = (v) => { const d = v.match(DOI); if (d) return d[1]; const a = v.match(ARXIV); return a ? "arXiv:" + a[1] : null; };
  const src = (hash, n) => hash ? ` <a class="k-src" href="${esc(API)}/trace.html?hash=${encodeURIComponent(hash)}${n ? "#call-" + encodeURIComponent(n) : ""}" target="_blank" rel="noopener" title="The Qloo request, its result and its limit">source</a>` : "";
  const post = async (path, body) => {
    const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.message || j.error || `the server answered ${r.status}`);
    return j;
  };
  const get = async (path) => { const r = await fetch(API + path); if (!r.ok) throw new Error(`the server answered ${r.status}`); return r.json(); };
  const said = (t) => { slot.innerHTML = `<p class="k-status" role="status"><span class="k-spin" aria-hidden="true"></span>${esc(t)}</p>`; };

  async function crossing(ref) {
    const j = await post("/api/cross", { ref });
    let since = 0;
    for (let i = 0; i < 240; i++) {
      const p = await get(`/api/cross?id=${encodeURIComponent(j.id)}&since=${since}`);
      since = p.total ?? since;
      const last = (p.steps || []).at(-1);
      if (last && last.title) said(last.title);
      if (p.status === "error") throw new Error(p.error || "the crossing stopped");
      if (p.report) return get("/api/report?hash=" + encodeURIComponent(p.report));
      if (p.status !== "running") throw new Error("the crossing ended without a demand check");
      await new Promise((ok) => setTimeout(ok, 500));
    }
    throw new Error("the crossing took too long");
  }

  // the launch cities on OpenStreetMap's tiles, at the closest zoom that holds them all; Qloo's heatmap points as
  // light rings. Tiles are asked only once a result is drawn (the first screen asks no host but its own)
  function map(cities, where = []) {
    const pts = cities.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon));
    if (!pts.length) return `<p class="k-none">Qloo named the cities but no coordinates came with them.</p>`;
    const W = 320, H = 200, T = 256;
    const px = (lat, lon, z) => { const n = T * 2 ** z, r = (lat * Math.PI) / 180;
      return [((lon + 180) / 360) * n, ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n]; };
    let z = 12;
    for (; z > 1; z--) {
      const xy = pts.map((c) => px(c.lat, c.lon, z)), xs = xy.map((q) => q[0]), ys = xy.map((q) => q[1]);
      if (Math.max(...xs) - Math.min(...xs) < W - 48 && Math.max(...ys) - Math.min(...ys) < H - 48) break;
    }
    const xy = pts.map((c) => px(c.lat, c.lon, z)), xs = xy.map((q) => q[0]), ys = xy.map((q) => q[1]);
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2, x0 = cx - W / 2, y0 = cy - H / 2;
    const n = 2 ** z, tiles = [];
    for (let tx = Math.floor(x0 / T); tx <= Math.floor((x0 + W) / T); tx++)
      for (let ty = Math.max(0, Math.floor(y0 / T)); ty <= Math.min(n - 1, Math.floor((y0 + H) / T)); ty++)
        tiles.push(`<img class="k-tile" alt="" loading="lazy" src="https://tile.openstreetmap.org/${z}/${((tx % n) + n) % n}/${ty}.png" style="left:${(tx * T - x0).toFixed(0)}px;top:${(ty * T - y0).toFixed(0)}px">`);
    const heat = where.filter((w) => Number.isFinite(w.lat) && Number.isFinite(w.lon)).map((w) => { const [x, y] = px(w.lat, w.lon, z);
      return `<span class="k-heat" style="left:${(x - x0).toFixed(0)}px;top:${(y - y0).toFixed(0)}px"></span>`; }).join("");
    const pins = pts.map((c, i) => `<span class="k-pin" title="${esc(c.name)}" style="left:${(xy[i][0] - x0).toFixed(0)}px;top:${(xy[i][1] - y0).toFixed(0)}px">${i + 1}</span>`).join("");
    return `<div class="k-osm" role="img" aria-label="Launch cities on a map: ${esc(pts.map((c) => c.name).join(", "))}">${tiles.join("")}${heat}${pins}` +
      `<a class="k-osm-credit" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a></div>` +
      (pts.some((c) => c.coords_from === "Wikidata") ? `<p class="k-fine">Coordinates: Wikidata</p>` : "");
  }

  // the answer Claude gave alone for the same idea (the published table behind "With and without Qloo"), beside Knos's
  let table = null;
  const norm = (t) => String(t || "").toLowerCase().replace(/\s+/g, " ").trim();
  async function claudeAlone(idea, mine) {
    table = table || await get("/api/qloo-diff").catch(() => ({ rows: [] }));
    const row = (table.rows || []).find((x) => norm(x.idea) === norm(idea));
    const c = row && row.claude;
    if (!c) return `<p class="k-none">Claude was not asked about this idea alone.</p>`;
    const side = (who, v) => `<div><h4>${who}</h4><p class="k-big">${esc((WORD[v.verdict] || [v.verdict || "-"])[0])}</p>
      <p>${esc(v.audience || "no audience")}</p><p>${esc((v.cities || []).join(", ") || "no cities")}</p><p>${esc(v.tier ? "price tier " + v.tier : "no price tier")}</p></div>`;
    return `<div class="k-vs">${side("Claude alone", c)}${side("Knos with Qloo", mine)}</div>${c.why ? `<p class="k-fine">Claude: ${esc(c.why)}</p>` : ""}`;
  }

  const WORD = { OPEN: ["Open for pre-orders", "open"], REFUSE: ["Not yet: pre-orders stay closed", "refuse"], CANNOT_DECIDE: ["Qloo cannot decide this one", "unknown"] };
  const TIERS = ["budget", "mid", "premium", "luxury"];
  const HEALTH = /\b(health\w*|patient\w*|medic\w*|clinic\w*|disease\w*|drug\w*|therap\w*|diagnos\w*|supplement\w*|glucose|diabet\w*)\b/i;
  function card(r, label) {
    const d = r.decision || {}, p = d.plan || {}, h = r.hash;
    let [word, cls] = WORD[d.verdict] || [String(d.verdict || "No verdict"), "unknown"];
    const who = r.who || {}, age = (p.who?.age || who.top_age || "").replace(/_/g, " ").replace(" and ", " and "), gender = p.who?.gender || who.top_gender || "";
    const segs = (p.who?.segments || (r.audiences || []).filter((a) => a.tied).map((a) => a.name)).filter(Boolean).slice(0, 3);
    // Qloo's audiences for the idea's own tags (or products), each naming what ties it: none is unrelated
    const wants = (r.who_wants || []).filter((a) => a && a.name && a.tie && a.tie.name).slice(0, 4);
    const launch = r.launch || {}, cities = ((r.cities || []).length ? r.cities : launch.cities || []).slice(0, 5);
    const where = (r.where || []).length ? r.where : launch.where || [], also = (r.also_love && r.also_love.domains) || [];
    const price = r.price || {}, tier = String(price.tier || "").toLowerCase();
    // which product Qloo read the idea as (kit SAFE_USE: ask when that choice changes the result): on a new check the
    // visitor can pick another match, or none of them; the verdict's reason is Knos's rule, apart from Qloo's data
    const lead = r.leader && typeof r.leader === "object" ? r.leader : null, why = (d.reasons || [])[0];
    const empty = !(age || gender) && !segs.length && !wants.length && !cities.length && !tier && !also.length;     // no part answered: one next step, no empty boxes
    if (empty && d.verdict !== "OPEN") [word, cls] = ["No taste data from Qloo", "unknown"];   // missing data is not a verdict
    const others = (r.matches || []).filter((m) => m && m.name && (!lead || m.id !== lead.id)).slice(0, 3);
    const read = lead ? `<p class="k-read" data-part="match">Read as <b>${esc(lead.name)}</b>${label ? "" : ` · Not it? ${others.map((m) =>
      `<button type="button" class="k-chip" data-pick="${esc(m.name)}">${esc(m.name)}</button>`).join(" ")} <button type="button" class="k-chip" data-none="${
      esc([lead.id, ...others.map((m) => m.id)].filter(Boolean).join(","))}">None of these</button>`}</p>` : "";
    return `<article class="k-card k-${cls}" data-verdict="${esc(d.verdict || "")}" data-not-prose>
  <header class="k-card-head"><p class="k-kick">${label ? `<span class="k-real">${esc(label)}</span> · ` : ""}${esc(r.idea || r.label || "")}</p><h2 class="k-verdict" data-part="verdict" data-qloo>${esc(word)}${src(h)}</h2>
  ${read}${why ? `<p class="k-why"><b>Knos rule:</b> ${esc(why)}</p>` : ""}</header>
  ${empty ? `<p class="k-next" data-part="next">Qloo has no taste data for this yet. Name who it is for and what it is like, as in "a vegan meal kit for students, like HelloFresh". Science, B2B or lab work: <a href="${esc(API)}/companies">companies mode</a>.</p>
  <form class="k-like" data-like><label>Most like <input name="like" maxlength="80" placeholder="a product or brand you know" aria-label="What is it most like?"></label> <button type="submit">Check</button></form>` : `<div class="k-parts">`}
    ${empty ? "" : `<section class="k-part" data-part="audience" data-qloo><h3>Who wants it</h3>
      ${age || gender ? `<p class="k-big">${esc([age, gender].filter(Boolean).join(", "))}</p>` : `<p class="k-none">Qloo did not answer who.</p>`}
      ${wants.length ? `<ul class="k-wants">${wants.map((a) => `<li><b>${esc(a.name)}</b> <span class="k-fine">tied by Qloo ${
        a.tie.kind === "tag" ? "tag" : "product"} ${esc(a.tie.name || "")}${a.tie.via ? `, through ${esc(a.tie.via)}` : ""}</span></li>`).join("")}</ul>`
        : segs.length ? `<p>${esc(segs.join(" · "))}</p>` : ""}${src(h, who.src)}</section>
    <section class="k-part k-where" data-part="cities" data-qloo><h3>Where to launch</h3>
      ${cities.length ? map(cities, where) + `<ol class="k-cities">${cities.map((c) => `<li>${esc(c.name)}${c.country ? ` <span class="k-fine">${esc(c.country)}</span>` : ""}</li>`).join("")}</ol>` : `<p class="k-none">Qloo named no launch city.</p>`}${!(r.cities || []).length && cities.length ? `<p class="k-fine">From the people of its taste.</p>` : ""}${src(h, cities[0]?.src)}</section>
    ${also.length ? `<section class="k-part" data-part="also" data-qloo><h3>They also love</h3>${also.map((d) =>
      `<p class="k-also" data-domain="${esc(d.domain)}"><b>${esc(d.domain === "music" ? "Music" : d.domain === "film" ? "Film" : d.domain)}</b> ${
      d.items.map((x) => esc(x.name)).join(", ")}${src(h, d.src)}</p>`).join("")}</section>` : ""}
    <section class="k-part" data-part="price" data-qloo><h3>Price tier</h3>
      ${tier ? `<ol class="k-tiers" aria-label="Price tier: ${esc(tier)}">${TIERS.map((t) => `<li${t === tier ? ' aria-current="true"' : ""}>${t}</li>`).join("")}</ol>` : `<p class="k-none">Qloo gave no price signal.</p>`}
${src(h, price.src)}</section>
  </div>`}
  <details class="k-claude" data-claude><summary>Claude alone</summary><div class="k-claude-body" data-claude-body></div></details>
  <footer class="k-card-foot"><p class="k-fine">Aggregate taste from Qloo: not causal, not a forecast, not about any one person.${
    HEALTH.test(r.idea || "") ? " Not medical advice: Qloo has no medical demand." : ""}</p>
    ${d.verdict === "OPEN" ? `<a class="k-cta" href="${esc(APP)}#buy=${esc(h)}">Open pre-orders for it →</a>` : `<a class="k-cta quiet" href="${esc(APP)}#research">Try it with a launch market →</a>`}</footer>
</article>`;
  }

  async function ask(v, extra = {}) {
    v = v.trim();
    if (!extra.exclude && !extra.leader) slot.dataset.ex = "[]";
    if (!v) { q.focus(); return; }
    go.disabled = true; root.setAttribute("aria-busy", "true");
    const ref = paper(v), t0 = performance.now();
    said(ref ? "Reading the paper…" : "Asking Qloo…");
    try {
      const r = ref ? await crossing(ref) : await post("/api/check", { idea: v, ...extra });
      slot.innerHTML = card(r);
      slot.last = r;
      slot.dataset.idea = v;
      delete slot.dataset.past;
      slot.dataset.ms = String(Math.round(performance.now() - t0));
      slot.querySelector(".k-verdict")?.focus?.();
    } catch (e) {
      slot.innerHTML = `<p class="k-err" role="alert">${esc(e.message || e)}. Try again, or <a href="${esc(APP)}#research">open the full crossing</a>.</p>`;
    } finally { go.disabled = false; root.removeAttribute("aria-busy"); }
  }
  // a link that names an idea (?q=, from the fields page) runs its check at once: one press, already pressed
  const asked = new URLSearchParams(location.search).get("q");
  if (asked) { q.value = asked.slice(0, 500); ask(q.value); }
  // proof first: the latest real verdict this server reached, drawn at load and labelled as a past check;
  // the visitor's own check replaces it
  const seen = (el, then) => {
    if (!("IntersectionObserver" in window)) return then();
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); then(); } });
    io.observe(el);
  };
  const draw = (r) => {
    if (!r || slot.dataset.ms || slot.querySelector(".k-status")) return;
    const when = String(r.checked_at || "").replace("T", " ").replace(/:\d\dZ$/, " UTC");
    slot.innerHTML = card(r, `Real check, ${when}`);
    slot.last = r;
    slot.dataset.past = "1";
    try { performance.mark("knos-proof-shown"); } catch { /* old browsers */ }   // when the past result was drawn
  };
  let carried = null;
  try { carried = JSON.parse(document.getElementById("k-proof")?.textContent || "null"); } catch { carried = null; }
  if (carried) draw(carried);                                  // in the page: at the first paint
  else seen(root, () => get("/api/proof").then((p) => draw(p && p.proof)).catch(() => {}));
  form.addEventListener("submit", (ev) => { ev.preventDefault(); ask(q.value); });
  // the newest payout to an agent, as the chain has it (the app reads the transaction back from devnet)
  const paid = document.getElementById("k-paid");
  if (paid) get("/api/agent/payout/latest").then((x) => {
    if (!x || !x.found || !(x.units > 0)) return;
    const day = String(x.at || "").slice(0, 10);
    paid.innerHTML = `An agent was paid <b>${esc(x.units)} test units</b> for verified work${day ? `, ${esc(day)}` : ""} · <a href="${esc(x.explorer)}" target="_blank" rel="noopener">the transaction</a>`;
    paid.hidden = false;
  }).catch(() => {});

  // the fold "Claude alone": filled when it is first opened, from the published table, beside this card's answer
  slot.addEventListener("toggle", async (ev) => {
    const box = ev.target;
    if (!(box instanceof HTMLDetailsElement) || !box.matches("[data-claude]") || !box.open) return;
    const body = box.querySelector("[data-claude-body]");
    if (!body || body.dataset.done) return;
    body.dataset.done = "1";
    const r = slot.last || {}, d = r.decision || {}, who = r.who || {}, p = d.plan || {};
    const cities = ((r.cities || []).length ? r.cities : (r.launch || {}).cities || []).slice(0, 3).map((c) => c.name);
    const mine = { verdict: d.verdict, audience: [(p.who?.age || who.top_age || "").replace(/_/g, " "), p.who?.gender || who.top_gender || ""].filter(Boolean).join(", ")
                     || (p.who?.segments || (r.audiences || []).filter((x) => x.tied).map((x) => x.name)).filter(Boolean).slice(0, 2).join(", "),
                   cities, tier: (r.price || {}).tier };
    body.innerHTML = await claudeAlone(r.idea || slot.dataset.idea, mine);
  }, true);
  slot.addEventListener("submit", (ev) => {                 // "most like ...": the named product is the one to compare with
    const f = ev.target.closest("[data-like]");
    if (!f) return;
    ev.preventDefault();
    const like = String(new FormData(f).get("like") || "").trim();
    if (like) ask(slot.dataset.idea || q.value, { leader: like });
  });
  root.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-q]"), pick = ev.target.closest("[data-pick]"), none = ev.target.closest("[data-none]");
    if (b) { q.value = b.dataset.q; ask(b.dataset.q); }
    else if (pick) ask(slot.dataset.idea || q.value, { leader: pick.dataset.pick });
    else if (none) {
      let prev = [];
      try { prev = JSON.parse(slot.dataset.ex || "[]"); } catch { prev = []; }
      const all = [...new Set([...prev, ...none.dataset.none.split(",").filter(Boolean)])].slice(-20);
      slot.dataset.ex = JSON.stringify(all);
      ask(slot.dataset.idea || q.value, { exclude: all });
    }
  });
})();
