// test_card_consistent, live: one city list per result. For each of the 6 recorded sample cards, pressed on the front
// door: the launch line's city, "Where to launch", the map's pins, the "Knos with Qloo" side of "Claude alone" (where
// that panel shows) and the /r/<id> page's launch cities are the same list (apps/wanted metros.launch_terms). A card
// that says "no launch city" or "no product matches" shows no "Launch in" line and no map. "Without Qloo", clicked
// within 200 ms of the card appearing, is pressed (aria-pressed="true") and stays pressed after the full card arrives.
//   node scripts/test_card_consistent.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_card_consistent.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const hashes = Object.fromEntries(Object.entries(JSON.parse(readFileSync(REC, "utf8")).cards).map(([k, v]) => [k, v.hash]));
const CARD = "#k-card > .k-card";
const browser = await chromium.launch();
const errors = [];
let agree = 0, mixed = 0, quick = 0;
const press = async (page, idea) => {
  await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  await page.click(`.k-try .k-chip[data-q="${idea.replace(/"/g, '\\"')}"]`).catch(() => page.fill("#k-q", idea).then(() => page.click("#k-go")));
};
try {
  // 1. the five places
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`1280: ${e.message}`));
  for (const idea of ideas) {
    await press(page, idea);
    await page.waitForSelector(`${CARD} [data-without]`, { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(4000);                                  // the full card, when a second one follows
    const claude = await page.$(`${CARD} details[data-claude]:not([hidden])`);
    if (claude) { await claude.evaluate((d) => { d.open = true; }); await page.waitForSelector(`${CARD} [data-claude-body] [data-cities]`, { timeout: 15000 }).catch(() => {}); }
    const c = await page.evaluate((sel) => { const k = document.querySelector(sel); const t = k?.querySelector('[data-part="terms"]');
      const sides = [...(k?.querySelectorAll("[data-claude-body] .k-vs > div") || [])];
      return { verdict: k?.querySelector(".k-verdict")?.firstChild?.textContent.trim() || "", why: k?.querySelector(".k-why")?.textContent || "",
        line: t ? t.dataset.city : null, where: [...(k?.querySelectorAll('[data-part="cities"] .k-cities li') || [])].map((li) => li.textContent.trim()),
        pins: [...(k?.querySelectorAll(".k-pin") || [])].map((p) => p.getAttribute("title")), map: !!k?.querySelector(".k-osm"),
        heading: !!k?.querySelector('[data-part="cities"] h3'), panel: sides.length > 1 ? sides[1].querySelector("[data-cities]")?.textContent.trim() : null }; }, CARD);
    const rp = await browser.newPage();
    await rp.goto(`${API}/r/${hashes[idea].slice(0, 16)}?t=${Date.now()}`, { waitUntil: "load" });
    const r = await rp.evaluate(() => ({ cities: document.querySelector("[data-cities]")?.textContent.trim() || null }));
    await rp.close();
    const L = r.cities ? r.cities.split(", ") : [];
    const panelList = c.panel == null ? null : c.panel === "no cities" ? [] : c.panel.split(", ");
    const same = (a) => JSON.stringify(a) === JSON.stringify(L);
    const equal = !!c.verdict && (c.line || null) === (L[0] || null) && same(c.where) && same(c.pins) && (panelList == null || same(panelList));
    const noCity = /no launch city/i.test(c.verdict) || /no product/i.test(c.why);
    const bad = noCity && (c.line != null || c.map || c.heading);
    agree += equal; mixed += bad;
    lines.push(`${equal && !bad ? "ok  " : "FAIL"} ${idea.slice(0, 38).padEnd(38)} "${c.verdict}": line ${c.line || "none"}; where [${c.where.join(" | ")}]; pins ${c.pins.length}; panel ${panelList == null ? "not shown" : `[${panelList.join(" | ")}]`}; /r/ [${L.join(" | ")}]`);
  }
  await ctx.close();
  ok(agree === ideas.length, `city lists equal across the launch line, Where to launch, the pins, Claude alone and /r/: ${agree} of ${ideas.length}`);
  ok(mixed === 0, `cards saying "no launch city" or "no product matches" with a launch line or a map: ${mixed}`);
  // 2. Without Qloo within 200 ms of the card, at both widths
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    const cx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    const p = await cx.newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    for (const idea of ideas) {
      await press(p, idea);
      const seen = await p.waitForSelector(`${CARD} [data-without][aria-pressed="false"]`, { timeout: 20000 }).then(() => true, () => false);
      if (!seen) { lines.push(`FAIL ${w} ${scheme} ${idea}: no card with Without Qloo: ${(await p.textContent("#k-card").catch(() => "")).slice(0, 160)}`); continue; }
      const t0 = Date.now();
      await p.click(`${CARD} [data-without]`, { timeout: 200 }).catch(() => {});
      const dt = Date.now() - t0;
      const now = await p.getAttribute(`${CARD} [data-without]`, "aria-pressed").catch(() => null);
      await p.waitForTimeout(4000);
      const later = await p.getAttribute(`${CARD} [data-without]`, "aria-pressed").catch(() => null);
      const good = dt <= 200 && now === "true" && later === "true";
      quick += good;
      lines.push(`${good ? "ok  " : "FAIL"} ${w} ${scheme} ${idea.slice(0, 38).padEnd(38)} Without Qloo clicked in ${dt} ms: aria-pressed ${now}, 4 s later ${later}`);
    }
    await cx.close();
  }
  ok(quick === ideas.length * 2, `Without Qloo pressed within 200 ms of the card: ${quick} of ${ideas.length * 2}`);
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_card_consistent: ${fails} check(s) failed`
  : `PASS test_card_consistent: ${agree} of ${ideas.length} recorded cards with one city list in every place shown; 0 "no launch city" or "no product" cards with a launch line or a map; Without Qloo pressed within 200 ms on ${quick} of ${ideas.length * 2}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
