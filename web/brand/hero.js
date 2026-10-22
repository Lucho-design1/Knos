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

  // cities at their latitude and longitude, on a frame fitted to them (graticule every 10 degrees)
  function map(cities) {
    const pts = cities.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon));
    if (!pts.length) return `<p class="k-none">Qloo named the cities but no coordinates came with them.</p>`;
    const lat = pts.map((c) => c.lat), lon = pts.map((c) => c.lon);
    let [x0, x1, y0, y1] = [Math.min(...lon), Math.max(...lon), Math.min(...lat), Math.max(...lat)];
    const padX = Math.max(8, (x1 - x0) * .2), padY = Math.max(5, (y1 - y0) * .25);
    x0 -= padX; x1 += padX; y0 -= padY; y1 += padY;
    const W = 320, H = Math.round(Math.min(220, Math.max(140, W * (y1 - y0) / (x1 - x0)))), X = (v) => ((v - x0) / (x1 - x0)) * W, Y = (v) => H - ((v - y0) / (y1 - y0)) * H;
    let grid = "";
    for (let g = Math.ceil(x0 / 10) * 10; g <= x1; g += 10) grid += `<line x1="${X(g).toFixed(1)}" y1="0" x2="${X(g).toFixed(1)}" y2="${H}"/>`;
    for (let g = Math.ceil(y0 / 10) * 10; g <= y1; g += 10) grid += `<line x1="0" y1="${Y(g).toFixed(1)}" x2="${W}" y2="${Y(g).toFixed(1)}"/>`;
    // each label beside its dot, on the side with room; a label that would cover another shows the city's number only
    const boxes = [], hit = (b) => boxes.some((o) => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0);
    const dots = pts.map((c, i) => {
      const x = X(c.lon), y = Y(c.lat), name = String(i + 1), w = name.length * 7 + 4;
      let label = null;
      for (const right of [x > W * .62, !(x > W * .62)]) {
        const b = right ? { x0: x - 10 - w, x1: x - 10 } : { x0: x + 10, x1: x + 10 + w };
        Object.assign(b, { y0: y - 8, y1: y + 8 });
        if (b.x0 >= 0 && b.x1 <= W && !hit(b)) { boxes.push(b); label = { right, text: name }; break; }
      }
      if (!label) { const b = { x0: x + 8, x1: x + 22, y0: y - 8, y1: y + 8 }; boxes.push(b); label = { right: false, text: String(i + 1) }; }
      return `<g><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${i === 0 ? 7 : 5}"/><text x="${(x + (label.right ? -10 : 10)).toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${label.right ? "end" : "start"}">${esc(label.text)}</text></g>`;
    }).join("");
    return `<svg class="k-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Launch cities on a map: ${esc(pts.map((c) => c.name).join(", "))}"><g class="k-grid">${grid}</g>${dots}</svg>` +
      (pts.some((c) => c.coords_from === "Wikidata") ? `<p class="k-fine">Coordinates: Wikidata</p>` : "");
  }

  const WORD = { OPEN: ["Open for pre-orders", "open"], REFUSE: ["Not yet: pre-orders stay closed", "refuse"], CANNOT_DECIDE: ["Qloo cannot decide this one", "unknown"] };
  const TIERS = ["budget", "mid", "premium", "luxury"];
  function card(r, label) {
    const d = r.decision || {}, p = d.plan || {}, h = r.hash, [word, cls] = WORD[d.verdict] || [String(d.verdict || "No verdict"), "unknown"];
    const who = r.who || {}, age = (p.who?.age || who.top_age || "").replace(/_/g, " ").replace(" and ", " and "), gender = p.who?.gender || who.top_gender || "";
    const segs = (p.who?.segments || (r.audiences || []).map((a) => a.name)).filter(Boolean).slice(0, 3);
    const cities = (r.cities || []).slice(0, 5), price = r.price || {}, tier = String(price.tier || "").toLowerCase();
    return `<article class="k-card k-${cls}" data-verdict="${esc(d.verdict || "")}" data-not-prose>
  <header class="k-card-head"><p class="k-kick">${label ? `<span class="k-real">${esc(label)}</span> · ` : ""}${esc(r.idea || r.label || "")}</p><h2 class="k-verdict" data-part="verdict" data-qloo>${esc(word)}${src(h)}</h2>
</header>
  <div class="k-parts">
    <section class="k-part" data-part="audience" data-qloo><h3>Who wants it</h3>
      ${age || gender ? `<p class="k-big">${esc([age, gender].filter(Boolean).join(", "))}</p>` : `<p class="k-none">Qloo did not answer who.</p>`}
      ${segs.length ? `<p>${esc(segs.join(" · "))}</p>` : ""}${src(h, who.src)}</section>
    <section class="k-part k-where" data-part="cities" data-qloo><h3>Where to launch</h3>
      ${cities.length ? map(cities) + `<ol class="k-cities">${cities.map((c) => `<li>${esc(c.name)}${c.country ? ` <span class="k-fine">${esc(c.country)}</span>` : ""}</li>`).join("")}</ol>` : `<p class="k-none">Qloo named no launch city.</p>`}${src(h, cities[0]?.src)}</section>
    <section class="k-part" data-part="price" data-qloo><h3>Price tier</h3>
      ${tier ? `<ol class="k-tiers" aria-label="Price tier: ${esc(tier)}">${TIERS.map((t) => `<li${t === tier ? ' aria-current="true"' : ""}>${t}</li>`).join("")}</ol>` : `<p class="k-none">Qloo gave no price signal.</p>`}
${src(h, price.src)}</section>
  </div>
  <footer class="k-card-foot"><p class="k-fine">Aggregate taste from Qloo: not causal, not a forecast, not about any one person.</p>
    ${d.verdict === "OPEN" ? `<a class="k-cta" href="${esc(APP)}#buy=${esc(h)}">Open pre-orders for it →</a>` : `<a class="k-cta quiet" href="${esc(APP)}#research">Try it with a launch market →</a>`}</footer>
</article>`;
  }

  async function ask(v) {
    v = v.trim();
    if (!v) { q.focus(); return; }
    go.disabled = true; root.setAttribute("aria-busy", "true");
    const ref = paper(v), t0 = performance.now();
    said(ref ? "Reading the paper…" : "Asking Qloo…");
    try {
      const r = ref ? await crossing(ref) : await post("/api/check", { idea: v });
      slot.innerHTML = card(r);
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
  // proof first: the latest real verdict this server reached, drawn at load and labelled as a past check (T3);
  // the visitor's own check replaces it
  const seen = (el, then) => {
    if (!("IntersectionObserver" in window)) return then();
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); then(); } });
    io.observe(el);
  };
  seen(root, () => get("/api/proof").then((p) => {
    const r = p && p.proof;
    if (!r || slot.dataset.ms || slot.querySelector(".k-status")) return;
    const when = String(r.checked_at || "").replace("T", " ").replace(/:\d\dZ$/, " UTC");
    slot.innerHTML = card(r, `Real check, ${when}`);
    slot.dataset.past = "1";
  }).catch(() => {}));
  form.addEventListener("submit", (ev) => { ev.preventDefault(); ask(q.value); });
  root.addEventListener("click", (ev) => { const b = ev.target.closest("[data-q]"); if (b) { q.value = b.dataset.q; ask(b.dataset.q); } });
})();
