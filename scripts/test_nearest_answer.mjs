// test_nearest_answer, live: 10 typed ideas, written here before the run and none of them a sample chip, each pressed on
// the front door while Qloo cannot answer. Each gets, within 5 s, either a full card from the nearest idea Qloo has
// answered (its first line "Nearest idea Qloo has answered: <idea>, live on <date>", then the verdict line, the
// audience, the launch line or the "Not yet" line, and the calls panel) or the 3 nearest answered ideas as buttons.
// No card says "cannot decide: no Qloo evidence".
//   node scripts/test_nearest_answer.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const IDEAS = ["a glow in the dark water bottle for hikers", "a quantum physics podcast for teens", "a recycled plastic sneaker for runners",
  "an encrypted email app for journalists", "a solar powered phone charger for festivals", "a meal planner app for busy parents",
  "a crypto savings app for students", "a smart watch that tracks hydration", "a bamboo cutting board brand", "a vintage vinyl record shop"];
const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_nearest_answer.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const browser = await chromium.launch();
const errors = [];
let answered = 0, cannot = 0, full = 0, offered = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  await page.fill("#k-q", "a warm up idea for the sleeping server"); await page.click("#k-go");   // the free server wakes first
  await page.waitForSelector("#k-card > .k-card", { timeout: 120000 }).catch(() => {});
  for (const idea of IDEAS) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea);
    const t0 = Date.now();
    await page.click("#k-go");
    const got = await page.waitForSelector("#k-card > .k-card", { timeout: 5000 }).then(() => true, () => false);
    const ms = Date.now() - t0;
    const c = await page.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
      return { text: k?.textContent || "", first: k?.querySelector("[data-qloo-down]")?.textContent.trim() || "", verdict: k?.querySelector(".k-verdict")?.firstChild?.textContent.trim() || "",
        audience: !!k?.querySelector('[data-part="audience"]'), terms: !!k?.querySelector('[data-part="terms"]'), calls: !!k?.querySelector('[data-part="calls"]'),
        options: [...(k?.querySelectorAll("[data-nearest-options] [data-q]") || [])].map((b) => b.dataset.q), kick: k?.querySelector(".k-kick")?.textContent.trim() || "" }; });
    const nearestLine = /^Nearest idea Qloo has answered: .+, live on \d{4}-\d{2}-\d{2}$/.test(c.first);
    const isFull = got && nearestLine && !!c.verdict && c.audience && (c.terms || c.verdict.startsWith("Not yet")) && c.calls;
    const isOffer = got && c.options.length === 3;
    const bad = /cannot decide: no Qloo evidence/i.test(c.text);
    full += isFull; offered += isOffer; cannot += bad;
    const good = (isFull || isOffer) && !bad && ms <= 5000;
    answered += good;
    lines.push(`${good ? "ok  " : "FAIL"} ${idea.padEnd(44)} ${ms} ms: ${isFull ? `"${c.first}" then "${c.verdict}"` : isOffer ? `3 buttons: ${c.options.join(" | ")}` : `no full card: "${c.text.slice(0, 120)}"`}`);
  }
} finally {
  await browser.close();
}
ok(answered === IDEAS.length, `typed ideas with a full card or 3 nearest buttons within 5 s: ${answered} of ${IDEAS.length} (${full} full cards, ${offered} with buttons)`);
ok(cannot === 0, `"cannot decide: no Qloo evidence" texts: ${cannot}`);
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_nearest_answer: ${fails} check(s) failed`
  : `PASS test_nearest_answer: ${answered} of ${IDEAS.length} typed ideas answered within 5 s (${full} full cards from the nearest answered idea, ${offered} with the 3 nearest as buttons); 0 "cannot decide: no Qloo evidence"`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
