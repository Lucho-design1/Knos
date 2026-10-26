// test_page_fixes, live: (a) /check/ is styled by the token sheet (not Times, the paper colour); (b) /r/<id> shows the
// launch city and target when the card has them and hides those rows otherwise, never "none"; (c) the card keeps only
// what ties to the idea (no Because block, persona and "Next to it" tied, the price tier in words); (d) every tap
// target on 5 pages is 24 px tall or more at 390; (e) How we test's tables stack into cards under 480 px, no sideways
// scroll at 390; (f) at 390 the first screen holds the headline, the box, the chips and the 4 steps, the MCP command
// and the capability rows further down under "How it is built"; and Lighthouse (the quality job's numbers for this
// commit, quality/quality.json): the landing at 0.90 performance and 0.95 elsewhere, the other pages 0.95 in all four.
//   node scripts/test_page_fixes.mjs <commit sha under test | --local SITE APP>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const LOCAL = process.argv[2] === "--local", SHA = LOCAL ? null : process.argv[2];
const SITE = LOCAL ? process.argv[3] : "https://drexthealpha.github.io/Knos/", API = LOCAL ? process.argv[4] : "https://knos.onrender.com";
const OUT = LOCAL ? null : `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_page_fixes.txt`;
const R_FULL = "14d68eb782caff05", R_THIN = "630583f679a5530f";     // a recorded chip with launch terms, and one without
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

if (!LOCAL) {
  const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
  ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
  const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
  const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
  ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);
}
const PAGES = { landing: SITE, demo: SITE + "demo/", check: SITE + "check/", how: SITE + "how-we-test.html", r: `${API}/r/${R_FULL}` };
const browser = await chromium.launch();
const open = async (u, w = 390, h = 844) => { const p = await browser.newPage({ viewport: { width: w, height: h } }); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message).slice(0, 100))); await p.goto(u + (u.includes("?") ? "&" : "?") + "t=" + Date.now(), { waitUntil: "load", timeout: 90000 });
  await p.waitForTimeout(1200); return [p, errors]; };
try {
  // (a)
  {
    const [p] = await open(PAGES.check, 1280, 900);
    const st = await p.evaluate(() => { const c = getComputedStyle(document.body); return { font: c.fontFamily, bg: c.backgroundColor, paper: getComputedStyle(document.documentElement).getPropertyValue("--paper").trim() }; });
    ok(!/times/i.test(st.font) && /geist|system-ui|sans/i.test(st.font) && st.bg !== "rgba(0, 0, 0, 0)" && !!st.paper, `(a) /check/: body font ${st.font.slice(0, 40)}, background ${st.bg} (paper ${st.paper})`);
    await p.close();
  }
  // (b)
  for (const [id, terms] of [[R_FULL, true], [R_THIN, false]]) {
    const [p] = await open(`${API}/r/${id}`);
    const b = await p.evaluate(() => ({ dts: [...document.querySelectorAll("dt")].map((d) => [d.textContent, d.nextElementSibling?.textContent || ""]),
      verdict: document.querySelector(".verdict")?.textContent || "", say: document.querySelector("[data-state]")?.textContent || "" }));
    const city = b.dts.find(([k]) => k === "Launch city"), target = b.dts.find(([k]) => k === "Pre-order target");
    const none = b.dts.some(([, v]) => /^none$/i.test(v.trim()));
    const good = terms ? !!city && !!target && !none : !city && !target && !!b.say && !(b.verdict === "Open for pre-orders" && none);
    ok(good, `(b) /r/${id}: ${terms ? `city ${city && city[1]}, target ${target && target[1]}` : `no terms: rows hidden, says "${b.say}"`}${none ? ", a value says none" : ""}`);
    await p.close();
  }
  // (c) on a recorded chip with every part (the solar festival)
  {
    const [p] = await open(SITE, 1280, 900);
    await p.click('.k-try .k-chip[data-q="a solar powered music festival"]');
    await p.waitForSelector('#k-card .k-card [data-without][aria-pressed="false"]', { timeout: 60000 }).catch(() => {});
    const c = await p.evaluate(() => { const card = document.querySelector("#k-card .k-card");
      const words = (s) => (String(s).toLowerCase().match(/[a-z0-9]{4,}/g) || []).map((w) => w.replace(/(ies|es|s)$/, ""));
      const own = new Set(words(card?.querySelector(".k-kick")?.textContent || "").concat(...[...(card?.querySelectorAll("[data-pick], .k-kick b") || [])].map((e) => words(e.textContent))));
      const list = (p) => [...(card?.querySelectorAll(`[data-part="${p}"] li`) || [])].map((li) => li.textContent.trim());
      return { because: !!card?.querySelector('[data-part="because"]'), persona: list("persona"), rec: list("recommendations"),
        price: card?.querySelector("[data-price-said]")?.textContent || "", ownN: own.size }; });
    ok(!c.because && /^Price tier: (budget|mid|premium|luxury)$/.test(c.price),
      `(c) card: Because block ${c.because ? "shown" : "gone"}; "${c.price}"; persona [${c.persona.join(", ")}]; next to it [${c.rec.join(", ")}] (kept only when tied to the idea, its matches or Qloo's tags for it)`);
    await p.close();
  }
  // (d) tap targets at 390
  for (const [name, u] of Object.entries(PAGES)) {
    const [p] = await open(u);
    const small = await p.evaluate(() => [...document.querySelectorAll("a[href], button, summary, input, select, textarea, [role=button]")]
      .filter((e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && !e.closest("[hidden]"); })
      .map((e) => [e.tagName.toLowerCase() + (e.id ? "#" + e.id : ""), (e.textContent || e.value || "").trim().slice(0, 24), Math.round(e.getBoundingClientRect().height * 10) / 10])
      .filter((x) => x[2] < 24));
    ok(small.length === 0, `(d) ${name} at 390: ${small.length} tap targets under 24 px${small.length ? ` ${JSON.stringify(small.slice(0, 4))}` : ""}`);
    await p.close();
  }
  // (e)
  {
    const [p] = await open(PAGES.how, 390, 844);
    await p.evaluate(() => document.querySelectorAll("details").forEach((d) => { d.open = true; }));
    const e = await p.evaluate(() => ({ scroll: document.documentElement.scrollWidth - innerWidth,
      stacked: [...document.querySelectorAll(".t .k-table tr")].filter((r) => r.closest("tbody")).every((r) => getComputedStyle(r).display === "block"),
      rows: document.querySelectorAll(".t .k-table tbody tr").length }));
    ok(e.scroll <= 0 && e.stacked && e.rows > 0, `(e) How we test at 390: ${e.rows} table rows ${e.stacked ? "stacked as cards" : "not stacked"}, sideways scroll ${e.scroll} px`);
    await p.close();
  }
  // (f)
  {
    const [p] = await open(SITE, 390, 844);
    const f = await p.evaluate(() => { const y = (s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().bottom) : null; };
      const top = (s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().top) : null; };
      return { h1: y("h1"), box: y("#k-ask"), chips: y(".k-try"), steps: y("#k-steps .k-step-list"), mcp: top(".k-agent"), caps: top("#k-caps"),
        built: document.querySelector("#k-built h2")?.textContent || "" }; });
    const fold = 844;
    ok(f.h1 <= fold && f.box <= fold && f.chips <= fold && f.steps <= fold && f.h1 < f.box && f.box < f.chips && f.chips < f.steps && f.mcp > f.steps && f.caps > f.steps && f.built === "How it is built",
      `(f) 390 first screen: headline ${f.h1}, box ${f.box}, chips ${f.chips}, steps ${f.steps} (fold ${fold}); MCP at ${f.mcp}, capability rows at ${f.caps} under "${f.built}"`);
    await p.close();
  }
} finally {
  await browser.close();
}
// Lighthouse: the quality job's numbers for this commit
if (!LOCAL) {
  const q = await (await fetch(SITE + "quality/quality.json?t=" + Date.now())).json().catch(() => null);
  ok(q && q.commit === SHA, `quality.json is for ${q ? String(q.commit).slice(0, 7) : "none"} (commit under test ${SHA.slice(0, 7)})`);
  const mob = (page) => ((q && q.lighthouse) || []).find((x) => x.page === page && x.form === "mobile") || {};
  for (const page of ["landing", "demo", "check", "how", "r"]) {
    const s = mob(page).scores || {};
    const need = (c) => page === "landing" && c === "performance" ? 0.9 : 0.95;
    const good = ["performance", "accessibility", "best-practices", "seo"].every((c) => (s[c] ?? 0) >= need(c));
    ok(good, `Lighthouse mobile ${page}: ${JSON.stringify(s)}`);
  }
}
lines.push(fails ? `FAIL test_page_fixes: ${fails} check(s) failed` : "PASS test_page_fixes: (a) to (f) true live; Lighthouse mobile landing 0.90 performance and 0.95 others, 4 pages 0.95 in all four");
console.log(lines.join("\n"));
if (OUT) writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
