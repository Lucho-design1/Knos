// The bar's three buttons on a page without web/front.js (the app, and the front door's own small pages): the phone's
// menu, "More", and light or dark (kept as "knos-theme", the key web/front.js uses, so both sites agree).
(() => {
  const $ = (id) => document.getElementById(id), root = document.documentElement;
  const bar = $("k-bar"), menu = $("menu"), more = $("more"), moreButton = $("more-button"), theme = $("theme");
  if (!bar || bar.dataset.ready) return;
  bar.dataset.ready = "1";
  root.classList.add("js");
  const fold = (open) => { more.classList.toggle("open", open); moreButton.setAttribute("aria-expanded", String(open)); };
  menu?.addEventListener("click", () => menu.setAttribute("aria-expanded", String(bar.classList.toggle("open"))));
  moreButton?.addEventListener("click", () => fold(!more.classList.contains("open")));
  document.addEventListener("click", (ev) => { if (more?.classList.contains("open") && (!more.contains(ev.target) || ev.target.closest("a"))) fold(false); });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (more?.classList.contains("open")) { fold(false); moreButton.focus(); }
    else if (bar.classList.contains("open")) { bar.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); menu.focus(); }
  });
  const set = (t) => { root.dataset.theme = t; try { localStorage.setItem("knos-theme", t); } catch { /* private mode */ } };
  try { const t = localStorage.getItem("knos-theme"); if (t) root.dataset.theme = t; } catch { /* private mode */ }
  if (theme) theme.onclick = () => set((root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark" ? "light" : "dark");
  // the link to the page being shown is marked, by its hash on a page that has views, else by its path
  const mark = () => {
    for (const a of bar.querySelectorAll("nav a")) {
      const u = new URL(a.href, location.href), here = u.origin === location.origin && u.pathname === location.pathname && (u.hash || "#home") === (location.hash.split("=")[0] || "#home");
      if (here) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
  };
  addEventListener("hashchange", mark); mark();
})();
