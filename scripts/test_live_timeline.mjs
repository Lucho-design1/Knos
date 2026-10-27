// test_live_timeline, live: on a recorded sample chip and on one nearest answer (P1), the card is drawn first and its Qloo
// calls follow as timeline rows one by one (Playwright samples at least 3 states of the row count), each row with its
// endpoint, what it decides, ms or "recorded <date>", and live or cached; when all are in, the counter "Qloo calls this
// check: N (live L, cached C)" equals the calls panel, and it names the month's calls left from /api/qloo/status.
//   node scripts/test_live_timeline.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_live_timeline.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const CASES = [["recorded chip", "a solar powered music festival"], ["nearest answer", "a glow in the dark water bottle for hikers"]];
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const browser = await chromium.launch();
const errors = [];
try {
  for (const [w, scheme] of [[1280, "light"], [390, "dark"]]) {
    const cx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    const p = await cx.newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    for (const [what, idea] of CASES) {
      await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
      await p.fill("#k-q", idea); await p.click("#k-go");
      await p.waitForFunction((i) => (document.querySelector("#k-card > .k-card")?.dataset.verdict ?? null) !== null && document.querySelector("#k-card > .k-card [data-timeline]"), idea, { timeout: 30000, polling: 10 }).catch(() => {});
      // the row count, sampled every 20 ms from the moment the card is in the page
      const states = await p.evaluate(async () => { const seen = [], t0 = performance.now();
        while (performance.now() - t0 < 6000) { const n = document.querySelectorAll("#k-card > .k-card [data-timeline] li").length; if (seen.at(-1) !== n) seen.push(n);
          await new Promise((r) => setTimeout(r, 20)); }
        return seen; });
      await p.waitForTimeout(1500);                          // the month's calls left, read once
      const s = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
        const panel = [...(k?.querySelectorAll('[data-part="calls"] li') || [])].map((li) => li.textContent);
        const rows = [...(k?.querySelectorAll("[data-timeline] li") || [])].map((li) => li.textContent);
        return { counter: k?.querySelector("[data-counter]")?.textContent.trim() || "", panel: panel.length, live: panel.filter((t) => / · live( · |$)/.test(t)).length,
          cached: panel.filter((t) => / · cached( · |$)/.test(t)).length, rows, first: k?.querySelector("[data-qloo-down]")?.textContent.trim() || "" }; });
      const m = s.counter.match(/^Qloo calls this check: (\d+) \(live (\d+), cached (\d+)\)( · Qloo's month: [\d,]+ of [\d,]+ calls left)?$/);
      const rowsOk = s.rows.length === s.panel && s.rows.every((t) => / · (decides|context|the verdict) · /.test(t) && /( ms| recorded \d{4}-\d{2}-\d{2}) · (live|cached)$/.test(t));
      const good = states.length >= 3 && states[0] < s.panel && m && Number(m[1]) === s.panel && Number(m[2]) === s.live && Number(m[3]) === s.cached && !!m[4] && rowsOk
        && (what !== "nearest answer" || s.first.startsWith("Nearest idea Qloo has answered:"));
      ok(good, `${w} ${scheme} ${what} (${idea}): ${states.length} states [${states.slice(0, 6).join(", ")}${states.length > 6 ? ", ..." : ""}]; "${s.counter}"; calls panel ${s.panel} (live ${s.live}, cached ${s.cached})`);
    }
    await cx.close();
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_live_timeline: ${fails} check(s) failed`
  : "PASS test_live_timeline: on a recorded chip and a nearest answer, at 390 and 1280, the rows came one by one (at least 3 states each) and the counter equals the calls panel, with the month's calls left");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
