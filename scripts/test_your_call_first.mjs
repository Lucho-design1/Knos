// test_your_call_first, live: with "Where would you launch it?" filled, a recorded sample card opens with "You said
// <city>. Qloo says <city>." and the difference in Qloo's concentration index, which equals the two cities' indexes on
// the card. Solar festival, guessed Miami, at 390 px and 1280 px.
//   node scripts/test_your_call_first.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_your_call_first.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const GUESS = "Miami", IDEA = "a solar powered music festival";
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
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    const p = await (await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme })).newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await p.fill("#k-guess", GUESS);
    await p.click(`.k-try .k-chip[data-q="${IDEA}"]`);
    await p.waitForSelector("#k-card > .k-card [data-guess]", { timeout: 60000 }).catch(() => {});
    const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card"), g = k?.querySelector("[data-guess]");
      return { first: k?.querySelector("p, h2")?.matches("[data-guess]") || false, text: g?.textContent.trim() || "", diff: g?.dataset.diff,
        city: k?.querySelector('[data-part="terms"]')?.dataset.city || "",
        idx: Object.fromEntries([...(k?.querySelectorAll(".k-cities li") || [])].map((li) => [li.querySelector("[data-city]")?.textContent.trim(), Number(li.querySelector("[data-index]")?.dataset.index)])) }; });
    const miami = Object.keys(c.idx).find((n) => n.toLowerCase().includes("miami"));
    const want = miami ? c.idx[c.city] - c.idx[miami] : NaN;
    const good = c.first && c.text.startsWith(`You said ${GUESS}. Qloo says ${c.city}.`) && Number(c.diff) === want && c.text.includes(`${Math.abs(want)} ${want >= 0 ? "higher" : "lower"}`);
    ok(good, `${w} ${scheme}: "${c.text}" (the card's indexes: ${c.city.split(/[-,]/)[0]} ${c.idx[c.city]}, ${miami ? miami.split(/[-,]/)[0] : "Miami"} ${miami ? c.idx[miami] : "none"})`);
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_your_call_first: ${fails} check(s) failed` : `PASS test_your_call_first: guessed ${GUESS} on ${IDEA}: the card opens with both cities and the index difference, at 390 and 1280`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
