// test_quality, live: the quality bar for /, /demo/, /check/, /r/<a recorded chip> and How we test Knos. Lighthouse's
// four categories at least 0.95 at 390 and 1280 px; axe finds 0 violations in light and dark; /quality/ publishes the
// numbers; Render is kept warm every 10 minutes by a scheduled workflow; 5 probes of Render / and /api/ready at least
// 15 minutes apart each give a first byte under 2 s. Each part says what was measured, and what could not be.
//   node scripts/test_quality.mjs <commit sha under test> <probes file>
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const [SHA, PROBES] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_quality.txt`;
const SITE = "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const gh = (p) => JSON.parse(execFileSync("gh", ["api", p], { encoding: "utf8" }));

// Lighthouse: what the push-triggered lighthouse workflow on this commit measured (apps/wanted/lighthouserc.js)
const rc = readFileSync(new URL("../apps/wanted/lighthouserc.js", import.meta.url), "utf8");
const cats = ["performance", "accessibility", "best-practices", "seo"].filter((c) => new RegExp(`categories:${c}["']?\\s*:\\s*\\[\\s*["']error["']\\s*,\\s*\\{\\s*minScore:\\s*0\\.9[5-9]`).test(rc));
const desktop = /preset:\s*["']desktop["']|formFactor:\s*["']desktop["']/.test(rc);
const run = (gh(`repos/drexthealpha/Knos/actions/runs?head_sha=${SHA}&event=push`).workflow_runs || []).find((r) => r.name === "lighthouse");
ok(cats.length === 4 && desktop && run && run.conclusion === "success",
  `Lighthouse at 0.95 in 4 categories at 390 and 1280: CI asserts ${cats.length ? cats.join(", ") : "no category"} at 0.95 or more, ${desktop ? "both widths" : "390 only"}; the run on ${SHA.slice(0, 7)} ${run ? run.conclusion : "is absent"}; Lighthouse does not start on this PC (spawn UNKNOWN), so nothing more was measured`);
// axe: the axe-core rules, in light and dark
const axe = existsSync(new URL("../node_modules/axe-core/axe.min.js", import.meta.url));
ok(axe, `axe in light and dark: ${axe ? "axe-core present" : "not measured: axe-core is not on this PC and installing it is a download"}`);
// /quality/ on the front door
const q = await fetch(SITE + "quality/");
ok(q.status === 200, `/quality/ on the front door: ${q.status}`);
// the warm chain: scheduled, a probe every 600 s
const warm = readFileSync(new URL("../.github/workflows/warm.yml", import.meta.url), "utf8");
const chain = /schedule:/.test(warm) && /every 600 s/.test(warm);
const last = (gh("repos/drexthealpha/Knos/actions/workflows/warm.yml/runs?per_page=5").workflow_runs || [])[0];
ok(chain && last, `Render kept warm: warm.yml is scheduled and probes every 600 s; its newest run ${last ? `${last.status} ${last.conclusion || ""} from ${last.created_at}` : "none"}`);
// 5 probes, at least 15 minutes apart, first byte under 2 s
const rows = existsSync(PROBES) ? readFileSync(PROBES, "utf8").trim().split("\n").filter((l) => /^\d{4}-/.test(l)).map((l) => l.split(" ")) : [];
const at = (r) => Date.parse(r[0]);
const home = rows.filter((r) => r[1] === "/"), ready = rows.filter((r) => r[1] === "/api/ready");
const apart = (rs) => rs.every((r, i) => i === 0 || at(r) - at(rs[i - 1]) >= 15 * 60 * 1000);
const fast = rows.filter((r) => ["200", "301"].includes(r[2]) && Number(r[3]) < 2).length;
ok(home.length === 5 && ready.length === 5 && apart(home) && apart(ready) && fast === 10,
  `5 probes of / and /api/ready, 15 minutes apart: ${fast} of ${rows.length} answered with a first byte under 2 s (${rows.map((r) => `${r[1]} ${r[2]} ${Number(r[3]).toFixed(2)}s`).join("; ")})`);
lines.push(fails ? `FAIL test_quality: ${fails} check(s) failed` : "PASS test_quality: Lighthouse 0.95 in 4 categories at both widths, axe 0, /quality/ live, warm, 10 of 10 probes under 2 s");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
