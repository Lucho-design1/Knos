// test_memory_panel, live: after 2 checks the "Your past checks" panel lists both, each with its verdict, its day and
// its line in the Knos record (read through GET /api/receipts?id=); the panel names Sibyl and links the record line;
// "Forget mine" empties the panel and this browser's storage and says what the public record keeps.
//   node scripts/test_memory_panel.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_memory_panel.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const IDEAS = ["a solar powered music festival", "a probiotic kombucha brand"];
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
  const p = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  for (const idea of IDEAS) {
    await p.fill("#k-q", idea); await p.click("#k-go");
    await p.waitForFunction((i) => [...document.querySelectorAll("[data-past-checks] [data-mine] li a")].some((a) => a.textContent === i), idea, { timeout: 60000 }).catch(() => {});
  }
  await p.waitForFunction(() => { const v = [...document.querySelectorAll("[data-past-checks] [data-v]")]; return v.length >= 2 && v.every((x) => !/reading the record/.test(x.textContent)); }, null, { timeout: 60000 }).catch(() => {});
  const s = await p.evaluate(() => { const b = document.querySelector("[data-past-checks]");
    return { text: b?.textContent || "", items: [...(b?.querySelectorAll("[data-mine] li") || [])].map((li) => ({ idea: li.querySelector("a")?.textContent, v: li.querySelector("[data-v]")?.textContent.trim(),
      record: li.querySelector("a[data-record]")?.href || "" })) }; });
  const both = IDEAS.every((i) => s.items.some((x) => x.idea === i && x.record));
  ok(both && s.items.length === 2, `after 2 checks the panel lists ${s.items.length}: ${s.items.map((x) => `${x.idea} (${x.v})`).join(" | ")}`);
  const links = await Promise.all(s.items.map(async (x) => x.record ? (await fetch(x.record)).status : 0));
  ok(/Sibyl/.test(s.text) && links.every((c) => c === 200) && s.items.every((x) => /#record$/.test(x.record)), `the panel names Sibyl and links each record line: ${s.items.map((x) => x.record.replace(/^https:\/\/knos\.onrender\.com/, "")).join(", ")} (${links.join(", ")})`);
  await p.click("[data-past-checks] [data-forget]");
  const f = await p.evaluate(() => ({ left: document.querySelectorAll("[data-past-checks] [data-mine] li").length, stored: localStorage.getItem("knos-past-checks"),
    said: document.querySelector("[data-past-checks] [data-forgot]")?.textContent || "" }));
  ok(f.left === 0 && f.stored === null && /public Knos record/.test(f.said), `Forget mine: ${f.left} left in the panel, storage ${f.stored === null ? "empty" : "kept"}; "${f.said}"`);
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_memory_panel: ${fails} check(s) failed` : "PASS test_memory_panel: after 2 checks the panel listed both with their Knos record lines; it names Sibyl and links the record; Forget mine emptied it");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
