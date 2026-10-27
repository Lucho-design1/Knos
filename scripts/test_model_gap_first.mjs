// test_model_gap_first, live: every recorded result with a model answer opens with "Model alone says <city>. Qloo says
// <city>.", then one number from /proof/ with its link; every recorded card shows what would flip its verdict and the
// options Knos rejected, each with its rule's code. 9 checks on the front door: the 7 ideas with a model answer and 2 without.
//   node scripts/test_model_gap_first.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_model_gap_first.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const MODEL = ["a solar powered music festival", "an ai recipe planner for families", "a crypto podcast for beginners", "a probiotic kombucha brand",
  "a recycled ocean plastic swimwear brand", "a quantum physics book for kids", "a smart water bottle that glows to remind you to drink"];
const OTHER = ["a vintage sneaker resale pop-up shop", "a password manager app"];
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const browser = await chromium.launch();
let sentences = 0, flips = 0, rejected = 0;
const errors = [];
try {
  const p = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "domcontentloaded", timeout: 90000 });
  for (const idea of [...MODEL, ...OTHER]) {
    await p.fill("#k-q", idea); await p.click("#k-go");
    await p.waitForFunction((i) => { const k = document.querySelector("#k-card > .k-card"); return k && !k.closest(".k-past") && k.querySelector(".k-kick")?.textContent.toLowerCase().includes(i) && k.querySelector("[data-part=flip]"); },
      idea, { timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(300);
    const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
      const first = k?.firstElementChild, h = k?.querySelector("[data-part=headline] a");
      return { first: first?.matches("[data-part=gap]") ? first.textContent.trim() : "", head: h ? [h.textContent.trim(), h.href] : null,
        flip: k?.querySelector("[data-part=flip]")?.textContent.trim() || "", rej: k?.querySelector("[data-part=rejected]")?.textContent.trim() || "",
        codes: [...(k?.querySelectorAll("[data-reject]") || [])].map((x) => [x.firstChild.textContent.trim(), x.dataset.code, x.querySelector("abbr")?.title || ""]) }; });
    const model = MODEL.includes(idea);
    const said = /^Model alone says [^.]+(\.[^.]+)*\. Qloo (says .+|names no city)\.$/.test(c.first);
    const head = !!c.head && /\d+ of \d+/.test(c.head[0]) && /\/Knos\/proof\/$/.test(c.head[1]);
    const flip = c.flip.startsWith("What would flip this verdict:");
    const rej = c.rej.startsWith("Options Knos rejected:") && (c.codes.length ? c.codes.every(([n, code, why]) => n && /^[A-Z_]+$/.test(code) && why) : /none/.test(c.rej));
    if (model) { sentences += said && head; }
    flips += flip; rejected += rej;
    ok((model ? said && head : true) && flip && rej, `${idea}: ${model ? `"${c.first}" | ${c.head ? c.head[0] : "no number"} | ` : ""}${c.flip.slice(0, 110)} | ${c.codes.length ? c.codes.map(([n, code]) => `${n.slice(0, 24)} ${code}`).join("; ") : c.rej.slice(0, 80)}`);
  }
} catch (e) {
  ok(false, `the browser step stopped: ${String(e.message).split("\n")[0].slice(0, 160)}`);
} finally {
  await browser.close();
}
ok(sentences === MODEL.length, `cards with a model answer that open with the sentence and /proof/'s number: ${sentences} of ${MODEL.length}`);
ok(flips === MODEL.length + OTHER.length && rejected === MODEL.length + OTHER.length, `cards with the flip line: ${flips}, with the rejected options and their codes: ${rejected}, of ${MODEL.length + OTHER.length}`);
ok(errors.length === 0, `page errors: ${errors.length}`);
lines.push(fails ? `FAIL test_model_gap_first: ${fails} check(s) failed`
  : `PASS test_model_gap_first: ${sentences} of 7 cards open with the model and Qloo cities and /proof/'s number; ${flips} of 9 show the flip line and ${rejected} of 9 the rejected options with codes`);
console.log(lines.join("\n"));
appendFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
