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

  // the parts of the card that read Qloo's answers already in the report (no new call): each value names its call
  // a Qloo label as the card shows it: title case, and no "(Lifestyle Preferences ...)" type suffix
  const qlabel = (s) => String(s || "").replace(/\s*\(Lifestyle Preferences[^)]*\)/gi, "").trim().replace(/(^|[\s/-])([a-z])/g, (m, a, b) => a + b.toUpperCase());
  let traceOf = "";
  const val = (n, html) => `<li data-call="${esc(n ?? "")}"><a class="k-val" href="${esc(API)}/trace.html?hash=${encodeURIComponent(traceOf)}#call-${esc(n ?? "")}" target="_blank" rel="noopener">${html}</a></li>`;
  function more(r) {
    const h = r.hash, ids = Object.fromEntries((r.matches || []).filter((m) => m && m.id).map((m) => [m.id, m.name]));
    traceOf = h || "";
    // a word of at least 4 letters, its plural folded: the words of the idea, its matched products and Qloo's tags for it
    const stems = (t) => String(t || "").toLowerCase().match(/[a-z0-9]{4,}/g)?.map((w) => w.replace(/(ies|es|s)$/, "")) || [];
    const own = new Set([r.idea, ...Object.values(ids), ...(r.tags || []).map((t) => (t && t.name) || t)].flatMap(stems));
    const tied = (x) => stems(x && x.name).some((w) => own.has(w));
    const vs = r.versus || null, persona = (r.persona || []).filter(tied), ladder = r.ladder || [],
      rec = ((r.recommended && r.recommended.items) || []).filter(tied);
    const parts = [];
    if (vs && (vs.whitespace || []).length) parts.push(`<section class="k-part" data-part="whitespace" data-qloo><h3>Room against ${esc(vs.leader)}</h3><ul class="k-vals">${
      vs.whitespace.slice(0, 6).map((w) => val(vs.src, esc(qlabel(w)))).join("")}</ul><p class="k-fine">overlap ${Math.round((vs.overlap || 0) * 100)}%</p>${src(h, vs.src)}</section>`);
    if (persona.length) parts.push(`<section class="k-part" data-part="persona" data-qloo><h3>Taste persona</h3><ul class="k-vals">${
      persona.slice(0, 6).map((t) => val(t.src, esc(qlabel(t.name)))).join("")}</ul>${src(h, persona[0].src)}</section>`);
    if (ladder.length) parts.push(`<section class="k-part" data-part="ladder" data-qloo><h3>Brand ladder</h3><ol class="k-vals">${
      ladder.slice(0, 6).map((b) => val(b.src, `${esc(b.name)} <span class="k-fine">${esc(Number(b.affinity || 0).toFixed(2))}</span>`)).join("")}</ol>${src(h, ladder[0].src)}</section>`);
    if (rec.length) parts.push(`<section class="k-part" data-part="recommendations" data-qloo><h3>Next to it</h3><ul class="k-vals">${
      rec.slice(0, 6).map((x) => val(r.recommended.src, esc(x.name))).join("")}</ul>${src(h, r.recommended.src)}</section>`);
    return parts.join("");
  }
  // the leader's weekly trend from /v2/trending (check.py _trend): its direction and the last week Qloo has
  const trendLine = (r) => { const t = r.trend || {};
    return t.data_through && t.direction ? `<p class="k-fine" data-part="trend">Trend of ${esc(t.entity || "the leader")}: ${esc(t.direction)}, data through ${esc(t.data_through)}${src(r.hash, t.src)}</p>` : ""; };
  // the same card with every Qloo answer removed, by the check's rule (check.py decide: no live Qloo evidence, no
  // verdict): no launch city, no pre-order target, and pre-orders cannot open. From the card's own data, offline.
  const without = (r) => `<article class="k-card k-unknown" data-verdict="CANNOT_DECIDE" data-without-qloo data-not-prose>
  <header class="k-card-head"><p class="k-kick">${esc(r.idea || "")} · without Qloo</p><h2 class="k-verdict">${esc(WORD.CANNOT_DECIDE[0])}</h2>
  <p class="k-why">With every Qloo answer removed there is no launch city and no pre-order target, so pre-orders cannot open.</p>
  <button type="button" class="k-chip" data-without aria-pressed="true">Without Qloo</button></header></article>`;
  slot.addEventListener("click", (ev) => {
    const b = ev.target instanceof Element && ev.target.closest("[data-without]");
    if (!b || !slot.last) return;
    slot.innerHTML = b.getAttribute("aria-pressed") === "true" ? card(slot.last) : without(slot.last);
    slot.querySelector("[data-without]")?.focus();
  });
  // every Qloo call behind the card: what it asked, how long it took and which part of the card it fed
  // the lists and the calls panel are styled when a card first needs them: the first screen's stylesheet stays within its
  // weight (tests/web/perf.mjs)
  const style = () => { if (document.getElementById("k-card-css")) return;
    document.head.insertAdjacentHTML("beforeend", `<style id="k-card-css">.k-vals{margin:0;padding-left:1.1em}.k-vals li{margin:0 0 4px}.k-val{color:inherit;text-decoration:none}.k-val:hover{text-decoration:underline}.k-calls{margin:var(--sp-3) var(--sp-5);font-size:var(--s-1)}.k-calls ol{margin:var(--sp-2) 0 0;padding-left:1.1em}.k-calls li{margin:0 0 4px;overflow-wrap:anywhere}</style>`); };
  function calls(r) {
    style();
    const fed = {}, add = (n, part) => { if (n != null) (fed[n] ||= new Set()).add(part); };
    (r.cities || []).forEach((c) => add(c.src, "launch cities"));
    (r.where || []).forEach((c) => add(c.src, "map"));
    add(r.who && r.who.src, "who wants it"); add(r.price && r.price.src, "price tier");
    ((r.also_love && r.also_love.domains) || []).forEach((d) => add(d.src, "they also love"));
    (r.persona || []).forEach((t) => add(t.src, "taste persona")); (r.ladder || []).forEach((b) => add(b.src, "brand ladder"));
    add(r.versus && r.versus.src, "room against the leader"); add(r.recommended && r.recommended.src, "next to it");
    (r.cities || []).filter((c) => (c.because || []).length).forEach((c) => add(c.src, "because"));
    const rows = (Array.isArray(r.calls) ? r.calls : []).map((c) => { const p = c.params || {};
      const keys = Object.keys(p).filter((k) => p[k] != null && p[k] !== "").map((k) => `${k}=${String(p[k]).slice(0, 40)}`).join(", ");
      return `<li data-call="${esc(c.n)}"><a href="${esc(API)}/trace.html?hash=${encodeURIComponent(r.hash || "")}#call-${esc(c.n)}" target="_blank" rel="noopener">#${esc(c.n)}</a> ${
        esc(c.call || "")} <span class="k-fine">${esc(keys)}</span> · ${Number.isFinite(c.ms) ? `${esc(c.ms)} ms` : `recorded ${esc(String(r.made || c.at || "").slice(0, 10))}`} · ${c.cached ? "cached" : "live"}${c.error ? " · failed" : ""} · ${esc([...(fed[c.n] || [])].join(", ") || String(c.effect || "").slice(0, 60) || "the verdict")}${r.signals ? ` · <span data-role="${(r.signals.decides || []).includes(c.n) ? "decides" : "context"}">${(r.signals.decides || []).includes(c.n) ? "decides" : "context"}</span>` : ""}</li>`; });
    return rows.length ? `<details class="k-calls" data-part="calls"><summary>Qloo calls (${rows.length})</summary><ol>${rows.join("")}</ol></details>` : "";
  }

  const WORD = { OPEN: ["Open for pre-orders", "open"], REFUSE: ["Not yet: pre-orders stay closed", "refuse"], CANNOT_DECIDE: ["Qloo cannot decide this one", "unknown"] };
  const TIERS = ["budget", "mid", "premium", "luxury"];
  const HEALTH = /\b(health\w*|patient\w*|medic\w*|clinic\w*|disease\w*|drug\w*|therap\w*|diagnos\w*|supplement\w*|glucose|diabet\w*)\b/i;
  function card(r, label) {
    const d = r.decision || {}, p = d.plan || {}, h = r.hash;
    let [word, cls] = WORD[d.verdict] || [String(d.verdict || "No verdict"), "unknown"];
    const who = r.who || {}, age = (p.who?.age || who.top_age || "").replace(/_/g, " ").replace(" and ", " and "), gender = p.who?.gender || who.top_gender || "";
    const segs = (p.who?.segments || (r.audiences || []).filter((a) => a.tied).map((a) => a.name)).filter(Boolean).slice(0, 3).map(qlabel);
    // Qloo's audiences for the idea's own tags (or products), each naming what ties it: none is unrelated
    const wants = (r.who_wants || []).filter((a) => a && a.name && a.tie && a.tie.name).slice(0, 4);
    const launch = r.launch || {}, terms = r.terms && r.terms.city ? r.terms : null;
    // Open needs a launch city: with none, pre-orders cannot open (apps/wanted metros.launch_terms is the one answer)
    if (d.verdict === "OPEN" && !terms && (r.stage !== "verdict" || r.no_map)) [word, cls] = ["Not yet: Qloo sets no launch city for this idea", "refuse"];
    // the cities of Qloo's heatmap, each a Census metro (apps/wanted metros.py); else Qloo's destinations
    const heat = ((terms && terms.metros) || []).map((m) => ({ name: m.city, lat: m.lat, lon: m.lon, src: (r.where || [])[0]?.src }));
    heat.sort((x, y) => (y.name === terms?.city) - (x.name === terms?.city));     // the launch city first, as the terms say
    const cities = (heat.length ? heat : (r.cities || []).length ? r.cities : launch.cities || []).slice(0, 5);
    const matched = Object.fromEntries((r.matches || []).filter((m) => m && m.id).map((m) => [m.id, m.name]));   // explainability's ids, named
    const where = ((r.where || []).length ? r.where : launch.where || []).slice(0, 8), also = (r.also_love && r.also_love.domains) || [];
    const price = r.price || {}, tier = String(price.tier || "").toLowerCase();
    // which product Qloo read the idea as (kit SAFE_USE: ask when that choice changes the result): on a new check the
    // visitor can pick another match, or none of them; the verdict's reason is Knos's rule, apart from Qloo's data
    const lead = r.leader && typeof r.leader === "object" ? r.leader : null, why = (d.reasons || [])[0];
    const empty = !(age || gender) && !segs.length && !wants.length && !cities.length && !tier && !also.length;     // no part answered: one next step, no empty boxes
    if (empty && d.verdict !== "OPEN" && !r.qloo_down) [word, cls] = ["No taste data from Qloo", "unknown"];   // a real empty answer only
    // Qloo not answering (apps/wanted recorded.py): said first, with the sample's last real card when there is one
    const at = (t) => String(t || "").replace("T", " ").slice(0, 16) + " UTC";
    const down = r.stale ? `Qloo is not answering right now (HTTP ${r.stale.code}). Showing the last real answer from ${at(r.stale.from)}.`
      : r.qloo_down ? `Qloo is not answering right now (HTTP ${r.qloo_down.code}). Try again in a few minutes.` : "";
    const others = (r.matches || []).filter((m) => m && m.name && (!lead || m.id !== lead.id)).slice(0, 3);
    const read = lead ? `<p class="k-read" data-part="match">Read as <b>${esc(lead.name)}</b>${label ? "" : ` · Not it? ${others.map((m) =>
      `<button type="button" class="k-chip" data-pick="${esc(m.name)}">${esc(m.name)}</button>`).join(" ")} <button type="button" class="k-chip" data-none="${
      esc([lead.id, ...others.map((m) => m.id)].filter(Boolean).join(","))}">None of these</button>`}</p>` : "";
    return `<article class="k-card k-${cls}" data-verdict="${esc(d.verdict || "")}" data-not-prose>
  ${down ? `<p class="k-terms" data-qloo-down>${esc(down)}</p>` : ""}
  <header class="k-card-head"><p class="k-kick">${label ? `<span class="k-real">${esc(label)}</span> · ` : ""}${esc(r.idea || r.label || "")}</p><h2 class="k-verdict" data-part="verdict" data-qloo>${esc(word)}${src(h)}</h2>
  ${terms ? `<p class="k-terms" data-part="terms" data-city="${esc(terms.city)}" data-target="${esc(terms.target)}">Launch in <b>${esc(terms.city)}</b>: ${esc(terms.target)} pre-orders. Every pre-order is refunded if the target is missed.</p>${terms.by_population ? `<p class="k-fine" data-part="by-population" data-pop-city="${esc(terms.by_population.city)}" data-pop-target="${esc(terms.by_population.target)}">By population: ${esc(terms.by_population.city)}, ${esc(terms.by_population.target)}. By Qloo taste: ${esc(terms.city)}, ${esc(terms.target)}.</p>` : ""}` : ""}
  ${r.signals && r.signals.line ? `<p class="k-fine" data-part="signals">${esc(r.signals.line)}</p>` : ""}
  ${read}${why ? `<p class="k-why"><b>Knos rule:</b> ${esc(why)}</p>` : ""}${trendLine(r)}
  ${r.decision ? `<button type="button" class="k-chip" data-without aria-pressed="false">Without Qloo</button>` : ""}</header>
  ${empty && r.no_map ? `<p class="k-terms" data-no-map>${esc(r.no_map)}</p>` : ""}
  ${empty && !r.qloo_down ? `<p class="k-next" data-part="next">Qloo has no taste data for this yet. Name who it is for and what it is like, as in "a vegan meal kit for students, like HelloFresh". Science, B2B or lab work: <a href="${esc(API)}/companies">companies mode</a>.</p>
  <form class="k-like" data-like><label>Most like <input name="like" maxlength="80" placeholder="a product or brand you know" aria-label="What is it most like?"></label> <button type="submit">Check</button></form>` : `<div class="k-parts">`}
    ${empty ? "" : `<section class="k-part" data-part="audience" data-qloo><h3>Who wants it</h3>
      ${age || gender ? `<p class="k-big">${esc([age, gender].filter(Boolean).join(", "))}</p>` : `<p class="k-none">Qloo did not answer who.</p>`}
      ${wants.length ? `<ul class="k-wants">${wants.map((a) => `<li><b>${esc(qlabel(a.name))}</b> <span class="k-fine">tied by Qloo ${
        a.tie.kind === "tag" ? "tag" : "product"} ${esc(a.tie.name || "")}${a.tie.via ? `, through ${esc(a.tie.via)}` : ""}</span></li>`).join("")}</ul>`
        : segs.length ? `<p>${esc(segs.join(" · "))}</p>` : ""}${src(h, who.src)}</section>
    <section class="k-part k-where" data-part="cities" data-qloo data-heat="${heat.length}"><h3>Where to launch</h3>
      ${cities.length ? map(cities, where) + `<ol class="k-cities">${cities.map((c) => `<li>${esc(c.name)}${c.country ? ` <span class="k-fine">${esc(c.country)}</span>` : ""}${
        (c.because || []).length ? `<br><span class="k-fine" data-because>because ${esc(c.because.map((id) => matched[id] || id).join(", "))}</span>` : ""}</li>`).join("")}</ol>` : r.stage === "verdict" ? `<p class="k-none" data-pending>Qloo's map is on its way.</p>` : `<p class="k-none">Qloo named no launch city.</p>`}${terms ? "" : r.no_map ? `<p class="k-terms" data-no-map>${esc(r.no_map)}</p>` : ""}${src(h, cities[0]?.src)}</section>
    ${also.length ? `<section class="k-part" data-part="also" data-qloo><h3>They also love</h3>${also.map((d) =>
      `<p class="k-also" data-domain="${esc(d.domain)}"><b>${esc(d.domain === "music" ? "Music" : d.domain === "film" ? "Film" : d.domain)}</b> ${
      d.items.map((x) => esc(x.name)).join(", ")}${src(h, d.src)}</p>`).join("")}</section>` : ""}
    <section class="k-part" data-part="price" data-qloo><h3>Price tier</h3>
      ${tier ? `<p class="k-tier-said" data-price-said>Price tier: ${esc(tier)}</p><ol class="k-tiers" aria-label="Price tier: ${esc(tier)}">${TIERS.map((t) => `<li${t === tier ? ' aria-current="true"' : ""}>${t}</li>`).join("")}</ol>` : `<p class="k-none">Qloo gave no price signal.</p>`}
${src(h, price.src)}</section>
    ${more(r)}
  </div>`}
  ${calls(r)}
  <details class="k-claude" data-claude hidden><summary>Claude alone</summary><div class="k-claude-body" data-claude-body></div></details>
  <footer class="k-card-foot"><p class="k-fine">Aggregate taste from Qloo: not causal, not a forecast, not about any one person.${
    HEALTH.test(r.idea || "") ? " Not medical advice: Qloo has no medical demand." : ""}</p>
    ${d.verdict === "OPEN" ? `<a class="k-cta" href="${esc(APP)}#buy=${esc(h)}">Open pre-orders for it →</a>` : `<a class="k-cta quiet" href="${esc(APP)}#research">Try it with a launch market →</a>`}${/^[0-9a-f]{16}/.test(h || "") ? ` <a class="k-cta quiet" href="${esc(API)}/r/${esc(h.slice(0, 16))}" data-share>Share this result</a>` : ""}</footer>
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
      // the verdict card first (verdict, matched product, audience); the map, also-loved and the launch terms follow
      // from the full check, whose Qloo questions the first one already sent
      const r = ref ? await crossing(ref) : await post("/api/check", { idea: v, ...extra, stage: "verdict" });
      slot.innerHTML = card(r);
      slot.last = r;
      slot.dataset.idea = v;
      delete slot.dataset.past;
      slot.dataset.ms = String(Math.round(performance.now() - t0));
      slot.querySelector(".k-verdict")?.focus?.();
      if (!ref && r.stage === "verdict") {
        const full = await post("/api/check", { idea: v, ...extra }).catch(() => null);
        if (full && slot.dataset.idea === v && slot.last === r) {
          const open = slot.querySelector("details[data-claude]")?.open;
          slot.innerHTML = card(full);
          slot.last = full;
          slot.dataset.full = String(Math.round(performance.now() - t0));
          if (open) slot.querySelector("details[data-claude]")?.setAttribute("open", "");
        }
      }
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
    // the last real check, folded to one line: the proof is on the first screen, the steps follow right under it
    const d = r.decision || {}, w = (WORD[d.verdict] || [d.verdict || ""])[0];
    slot.innerHTML = `<details class="k-more k-past"><summary>Real check, ${esc(when)}: ${esc(r.idea || "")}, ${esc(w)}</summary>${card(r, `Real check, ${when}`)}</details>`;
    slot.last = r;
    slot.dataset.past = "1";
    try { performance.mark("knos-proof-shown"); } catch { /* old browsers */ }   // when the past result was drawn
  };
  form.addEventListener("submit", (ev) => { ev.preventDefault(); ask(q.value); });
  // below the first screen: the newest payout to an agent, as the chain has it, and the usage counter (checks and
  // briefs from the app's store, the payment program's devnet transactions). The build wrote both into the page
  // (scripts/live_snapshot.py); they are asked again after the reader's first move, as the product list is (web/home.js)
  let moved = false;
  const later = (f) => { const go = () => { if (moved) return; moved = true; f(); };
    for (const t of ["pointermove", "pointerdown", "touchstart", "keydown", "scroll", "focusin"]) addEventListener(t, go, { once: true, passive: true, capture: true }); };
  // and only once Paid on proof is in view: the first screen asks nobody
  later(() => seen(document.getElementById("paid-on-proof") || root, () => {
    const paid = document.getElementById("k-paid"), use = document.getElementById("k-usage"), oidc = document.getElementById("k-oidc");
    // the newest signature check knos_oidc ran on devnet (the program reads GitHub's signature itself), from devnet
    // the program's address is read from the program_ids.json the build ships, never typed into the page
    if (oidc) fetch("program_ids.json").then((r) => r.json()).then((ids) => fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignaturesForAddress", params: [ids.knos_oidc, { limit: 20, commitment: "confirmed" }] }) }))
      .then((r) => r.json()).then((j) => {
        const x = (j.result || []).find((t) => t.err === null);
        if (!x) return;
        const day = x.blockTime ? new Date(x.blockTime * 1000).toISOString().slice(0, 10) : "";
        oidc.innerHTML = `Latest signature check on devnet${day ? `, ${esc(day)}` : ""} · <a href="https://explorer.solana.com/tx/${esc(x.signature)}?cluster=devnet" target="_blank" rel="noopener">the transaction</a>`;
        oidc.dataset.live = "1";
      }).catch(() => {});
    if (paid) get("/api/agent/payout/latest").then((x) => {
      if (!x || !x.found || !(x.units > 0)) return;
      const day = String(x.at || "").slice(0, 10);
      // what released it is the link to its transaction: twelve words at most for the line (tests/test_site_overflow.py)
      paid.innerHTML = `Agent paid <b>${esc(x.units)} test units</b>${day ? `, ${esc(day)}` : ""} · <a href="${esc(x.explorer)}" target="_blank" rel="noopener">${esc(x.released || "the transaction")}</a>`;
      paid.hidden = false;
      paid.dataset.live = "1";
    }).catch(() => {});
    // outside use only, this week against the last: a line only for real growth from at least 10, else nothing
    if (use) get("/api/usage").then((u) => {
      const line = u && u.trend && u.trend.line;
      use.textContent = line || "";
      use.hidden = !line;
      use.dataset.live = "1";
    }).catch(() => {});
  }));

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
  // "Claude alone" is shown only when the published table has Claude's answer for this idea; a card drawn by a press
  // asks (the past result in its fold, drawn at the first paint, asks nobody)
  new MutationObserver(async () => {
    const box = slot.querySelector("details[data-claude][hidden]");
    if (!box || box.closest(".k-past") || box.dataset.asked) return;
    box.dataset.asked = "1";
    table = table || await get("/api/qloo-diff").catch(() => ({ rows: [] }));
    const idea = (slot.last || {}).idea || slot.dataset.idea;
    if ((table.rows || []).some((x) => x.claude && norm(x.idea) === norm(idea))) box.hidden = false;
  }).observe(slot, { childList: true });
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
  // the past result, drawn last: every chip and the box already answer, and a snapshot the card cannot read leaves
  // the first screen as it is (the chips still check)
  const shown = (r) => { try { draw(r); } catch (e) { console.warn("knos: the past result was not drawn", e); } };
  let carried = null;
  try { carried = JSON.parse(document.getElementById("k-proof")?.textContent || "null"); } catch { carried = null; }
  if (carried) shown(carried);                                 // in the page: at the first paint
  else seen(root, () => get("/api/proof").then((p) => shown(p && p.proof)).catch(() => {}));
})();
