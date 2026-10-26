// test_target_from_qloo, live: /demo/ and the J3 crossing page show the D2 target in each of Qloo's launch cities for
// the J3 idea, "floor" where max(10, ...) binds, and a second worked example (the D2 idea with the largest target at or
// below 200 where the floor does not bind), at 390 and 1280 px; each T recomputes from its inputs.
//   node scripts/test_target_from_qloo.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_target_from_qloo.txt`;
const SITE = "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const browser = await chromium.launch();
let firstRows = 0, second = null;
try {
  for (const [name, u] of [["demo", SITE + "demo/"], ["crossing", SITE + "crossing/7b4ed16b8c2903dc/"]]) {
    for (const [w, h] of [[390, 844], [1280, 900]]) {
      const p = await browser.newPage({ viewport: { width: w, height: h } });
      await p.goto(u + "?t=" + Date.now(), { waitUntil: "load" });
      const t = await p.evaluate(() => ({ scroll: document.documentElement.scrollWidth - innerWidth,
        tables: [...document.querySelectorAll("table.targets")].map((tb) => [...tb.querySelectorAll("tbody tr")].map((r) => ({
          city: r.cells[0].textContent.trim(), aff: Number(r.dataset.aff), pop: Number(r.dataset.pop), t: Number(r.dataset.t),
          shownPop: Number(r.cells[2].textContent.replace(/,/g, "")), shownAff: Number(r.cells[1].textContent), shownT: Number(r.cells[3].querySelector("b")?.textContent),
          floor: !!r.querySelector(".floor"), visible: r.getBoundingClientRect().width > 0 }))) }));
      const rows = t.tables.flat();
      const right = rows.every((r) => { const raw = Math.round(r.pop / 100000 * r.aff); return r.t === Math.max(10, raw) && r.shownT === r.t && r.shownPop === r.pop && r.shownAff === r.aff && r.floor === (raw < 10) && r.visible; });
      ok(t.tables.length === 2 && rows.length >= 2 && right && t.scroll <= 0, `${name} at ${w}: ${t.tables.length} tables, ${rows.length} rows recompute (${rows.map((r) => `${r.city} ${r.t}${r.floor ? " floor" : ""}`).join("; ")}), sideways scroll ${t.scroll}`);
      firstRows = t.tables[0] ? t.tables[0].length : 0;
      second = t.tables[1] && t.tables[1][0];
      await p.close();
    }
  }
} finally {
  await browser.close();
}
ok(second && second.t > 10 && second.t <= 200 && !second.floor, `second example: ${second && second.city}, affinity ${second && second.aff}, population ${second && second.pop}, T ${second && second.t}`);
ok(firstRows === 5, firstRows === 5 ? "the J3 idea's top 5 launch cities" :
  `BLOCKED: the J3 idea's top 5 launch cities: the D2 run log keeps each idea's top metro only (${firstRows} shown); the other 4 need a new heatmap call and Qloo answers 429`);
lines.push(fails ? `FAIL test_target_from_qloo: ${fails} check(s) failed` : `PASS test_target_from_qloo: both tables at 390 and 1280 on both pages, every T recomputes, second example T ${second.t}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
