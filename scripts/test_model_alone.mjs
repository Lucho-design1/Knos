// test_model_alone, live: the 6 recorded sample chips and the 2 D2 worked examples. Each recorded card has a "With Qloo /
// Model alone" switch; pressed, it shows the model's recorded launch city and reasoning (claude -p, no Qloo) beside
// Knos's launch city and audience, with what differs marked, and With Qloo hides it again; at 390 px and 1280 px. An
// idea with no recorded card is BLOCKED.
//   node scripts/test_model_alone.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_model_alone.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const IDEAS = ["an AI recipe planner for families", "a crypto podcast for beginners", "a quantum physics book for kids", "a solar powered music festival",
  "a probiotic kombucha brand", "a recycled ocean plastic swimwear brand", "a graphene-coated cycling jacket", "a smart water bottle that glows to remind you to drink"];
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const doc = JSON.parse(readFileSync(REC, "utf8"));
const key = (t) => String(t || "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const recorded = new Set([...Object.keys(doc.cards || {}), ...Object.keys(doc.answered || {})].map(key));
const model = Object.fromEntries(Object.entries(doc.model_alone || {}).map(([k, v]) => [key(k), v]));
ok(IDEAS.every((i) => model[key(i)] && model[key(i)].city), `model-alone answers recorded: ${IDEAS.filter((i) => model[key(i)]?.city).length} of ${IDEAS.length}`);
const browser = await chromium.launch();
const errors = [];
let both = 0;
try {
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    const cx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    const p = await cx.newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    for (const idea of IDEAS) {
      if (!recorded.has(key(idea))) {
        lines.push(`FAIL ${w} ${scheme} ${idea}: BLOCKED: no recorded card for this idea exists (the D2 run kept its launch terms only, and Qloo has refused since 25 Oct)`);
        fails++;
        continue;
      }
      await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
      await p.fill("#k-q", idea); await p.click("#k-go");
      await p.waitForSelector('#k-card > .k-card [data-view="model"]', { timeout: 60000 }).catch(() => {});
      await p.click('#k-card > .k-card [data-view="model"]').catch(() => {});
      const s = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card"), panel = k?.querySelector("[data-model-panel]");
        const cell = (row, who) => panel?.querySelector(`tr[data-row="${row}"] td[data-${who}]`)?.textContent.trim() || "";
        return { kick: k?.querySelector(".k-kick")?.textContent.trim() || "", shown: !!panel && !panel.hidden && panel.checkVisibility(), pressed: k?.querySelector('[data-view="model"]')?.getAttribute("aria-pressed"),
          knosCity: cell("city", "knos"), modelCity: cell("city", "model"), modelWhy: cell("why", "model"), marks: panel?.querySelectorAll("mark").length || 0,
          terms: k?.querySelector('[data-part="terms"]')?.dataset.city || null, over: document.documentElement.scrollWidth - innerWidth }; });
      await p.click('#k-card > .k-card [data-view="qloo"]').catch(() => {});
      const back = await p.evaluate(() => document.querySelector("#k-card > .k-card [data-model-panel]")?.hidden === true);
      const m = model[key(idea)];
      const good = s.shown && s.pressed === "true" && s.modelCity === m.city && s.modelWhy === m.why && s.knosCity === (s.terms || "no launch city") && s.marks >= 1 && back && s.over <= 0;
      both += good;
      lines.push(`${good ? "ok  " : "FAIL"} ${w} ${scheme} ${idea.slice(0, 40).padEnd(40)} Knos ${s.knosCity || "?"} | model ${s.modelCity || "?"}; ${s.marks} marked; ${back ? "With Qloo hides it" : "does not hide"}`);
      if (!good) fails++;
    }
    await cx.close();
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_model_alone: ${both / 2} of ${IDEAS.length} recorded cards show both answers at both widths; ${fails} check(s) failed`
  : `PASS test_model_alone: ${IDEAS.length} of ${IDEAS.length} recorded cards show both answers, the switch working at 390 and 1280`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
