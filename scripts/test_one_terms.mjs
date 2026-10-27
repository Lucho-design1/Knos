// test_one_terms, live: one launch-terms answer (apps/wanted metros.launch_terms) on every page. For each of the 6
// recorded sample cards: the card's city (its top row and the first of "Where to launch"), the /r/ page's and the
// trace's terms (GET /api/report) are equal, the card's target equals the /r/ target, and no page says "Open for
// pre-orders" without a city. The 2 chips with no recording give way to one line.
//   node scripts/test_one_terms.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_one_terms.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
let same = 0, openNoCity = 0;
try {
  const front = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await front.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  const chips = await front.evaluate(() => ({ n: document.querySelectorAll(".k-try .k-chip[data-q]").length, more: document.querySelector("[data-more-chips]")?.textContent.trim() || "" }));
  ok(chips.n === 6 && chips.more === "2 more examples return when Qloo answers again", `chips: ${chips.n} with recordings, line "${chips.more}"`);
  for (const [idea, c] of Object.entries(cards)) {
    const id = c.hash.slice(0, 16);
    await front.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await front.fill("#k-q", idea); await front.click("#k-go");
    await front.waitForSelector('#k-card .k-card [data-without][aria-pressed="false"]', { timeout: 60000 }).catch(() => {});
    const card = await front.evaluate(() => { const k = document.querySelector("#k-card .k-card");
      const t = k?.querySelector('[data-part="terms"]');
      return { verdict: k?.querySelector(".k-verdict")?.firstChild?.textContent.trim() || "", city: t?.dataset.city || null, target: t ? Number(t.dataset.target) : null,
        first: k?.querySelector('[data-part="cities"] li')?.firstChild?.textContent.trim() || null, row: t?.textContent.trim() || "" }; });
    const rp = await browser.newPage();
    await rp.goto(`${API}/r/${id}?t=${Date.now()}`, { waitUntil: "load" });
    const r = await rp.evaluate(() => { const dt = [...document.querySelectorAll("dt")]; const v = (k) => dt.find((d) => d.textContent === k)?.nextElementSibling?.textContent || null;
      return { verdict: document.querySelector(".verdict")?.textContent || "", city: v("Launch city"), target: v("Pre-order target") ? parseInt(v("Pre-order target"), 10) : null }; });
    await rp.close();
    const rep = await (await fetch(`${API}/api/report?hash=${c.hash}`)).json().catch(() => ({}));
    const tr = rep && rep.terms && rep.terms.city ? { city: rep.terms.city, target: rep.terms.target } : { city: null, target: null };
    const row = card.city ? card.row === `Launch in ${card.city}: ${card.target} pre-orders. Every pre-order is refunded if the target is missed.` : true;
    const equal = card.city === r.city && r.city === tr.city && card.target === r.target && r.target === tr.target && (!card.city || card.first === card.city) && row;
    const bad = (card.verdict === "Open for pre-orders" && !card.city) + (r.verdict === "Open for pre-orders" && !r.city);
    same += equal; openNoCity += bad;
    lines.push(`${equal && !bad ? "ok  " : "FAIL"} ${idea.slice(0, 38).padEnd(38)} card ${card.city || "no city"} ${card.target ?? ""} (first listed ${card.first || "none"}), /r/ ${r.city || "no city"} ${r.target ?? ""}, trace ${tr.city || "no city"} ${tr.target ?? ""}; "${card.verdict}" / "${r.verdict}"`);
  }
  await front.close();
} finally {
  await browser.close();
}
ok(same === 6, `card, /r/ and trace agree on city and target: ${same} of 6`);
ok(openNoCity === 0, `pages saying "Open for pre-orders" without a city: ${openNoCity}`);
lines.push(fails ? `FAIL test_one_terms: ${fails} check(s) failed` : `PASS test_one_terms: 6 of 6 recorded cards agree on city and target across card, /r/ and trace; 0 Open without a city`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
