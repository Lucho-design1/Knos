// THE FIRST SCREEN: research products people can back now, each with its one-tap actions (Back it, Fund a milestone,
// Contribute). The cards in index.html (#home-products) are a snapshot the site ships (scripts/front_snapshot.py writes
// them from the app's GET /api/front), so the page is whole before anything answers. With the reader's first move this
// module asks the app (apps/wanted at knos.onrender.com, a free instance that sleeps: the ask also wakes it) for the
// live list and redraws the cards in place when it answers; it never waits for it, and an empty or failed answer leaves
// the snapshot.
// A press on an action goes straight to the app when it answers within a moment, else to the wake page (wanted.html),
// which forwards the same action once the app is awake. Money: Solana devnet test units.
export const APP = "https://knos.onrender.com";
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SLUG = /^[a-z0-9-]{3,64}$/;
// a product's name is a statement of the first screen: twelve words at most (tests/test_site_overflow.py)
export const title = (t) => { const w = String(t || "").trim().split(/\s+/); return w.length > 12 ? `${w.slice(0, 11).join(" ")}…` : w.join(" "); };

// One card, the same markup scripts/front_snapshot.py writes: what it is, the research behind it, how far its backing is.
export function cardHTML(p) {
  const slug = SLUG.test(String(p.slug)) ? p.slug : "";
  const reserve = Math.max(0, Number(p.reserve_units) || 0), backed = Math.max(0, Number(p.backed_units) || 0);
  const fill = reserve ? Math.max(2, Math.min(100, Math.round((100 * backed) / reserve))) : 2;
  const act = (what, label, cls) => `<a class="k-btn${cls}" href="wanted.html#${what}=${slug}" data-app="#${what}=${slug}">${label}</a>`;
  return `<li class="hp" data-slug="${esc(slug)}"><p class="hp-src">${p.tech_name ? esc(p.tech_name) + " · " : ""}${esc(p.paper || "Your idea")}${p.maker ? "" : " · maker wanted"}</p>`
    + `<h3 class="hp-t">${esc(title(p.title))}</h3>${backed ? `<div class="hp-bar" aria-hidden="true"><i style="width:${fill}%"></i></div>` : ""}`
    + `<p class="hp-act">${act("back", "Back it", "")} ${act("fund", "Fund the work", " quiet")} ${act("contribute", "Contribute", " quiet")}</p></li>`;
}

// The live list, drawn in place of the snapshot: only an answer that holds products replaces it.
export async function refresh(el, { fetchImpl = globalThis.fetch, timeout = 9000, when = document.getElementById("home-when") } = {}) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetchImpl(`${APP}/api/front`, { signal: ctl.signal, cache: "no-store" });
    const b = r.ok ? await r.json() : null;
    const rows = (b && Array.isArray(b.products) ? b.products : []).filter((p) => p && SLUG.test(String(p.slug)) && p.title).slice(0, 3);
    if (!rows.length) return false;
    el.innerHTML = rows.map(cardHTML).join("");
    el.dataset.live = "1";
    if (when) when.textContent = "Live now · devnet test money";
    return true;
  } catch { return false; } finally { clearTimeout(timer); }
}

let started = false;
export function initHome(doc = document) {
  const el = doc.getElementById("home-products");
  if (!el || started) return;
  started = true;
  (doc.getElementById("view-home") || el).addEventListener("click", (ev) => {
    const a = ev.target.closest?.("a[data-app]");
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;      // a new tab keeps the wake page
    ev.preventDefault();
    const late = new Promise((res) => setTimeout(() => res(false), 1500));
    const ping = fetch(`${APP}/healthz`, { mode: "no-cors", cache: "no-store" }).then(() => true, () => false);
    Promise.race([ping, late]).then((awake) => { location.href = awake ? `${APP}/app/${a.dataset.app}` : a.getAttribute("href"); });
  });
  // the live list is asked for with the reader's first move (a touch, a scroll, a key, the pointer), as the round under
  // the check's first screen is: the snapshot is the page until then, and a page nobody touches asks no other host
  let asked = false;
  const go = () => { if (asked) return; asked = true; refresh(el); };
  for (const t of ["pointermove", "pointerdown", "touchstart", "keydown", "scroll", "focusin"]) addEventListener(t, go, { once: true, passive: true, capture: true });
}
