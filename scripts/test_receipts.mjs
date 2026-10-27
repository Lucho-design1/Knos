// test_receipts, live: on each of the 6 recorded sample cards, every source chip (Qloo, rule, model or chain, at most
// 16 px tall) opens a receipt row with its id and the same source, and the card links its Receipts. On each receipts
// page every hash recomputes: a Qloo call's from the call's JSON as shown, the Ready brief's with knos.ready from the
// brief; the Knos record line names its sequence number.
//   node scripts/test_receipts.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_receipts.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

// canonical JSON as Python's json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False) writes it
const canon = (v) => v === null || typeof v !== "object" ? JSON.stringify(v) : Array.isArray(v) ? `[${v.map(canon).join(",")}]`
  : `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(",")}}`;
const sha = (s) => createHash("sha256").update(s, "utf8").digest("hex");
const ready = (brief) => execFileSync(py, ["-c", "import json,sys; from knos import ready; print(ready.criteria_hash(json.load(sys.stdin)))"],
  { input: JSON.stringify(brief), encoding: "utf8", cwd: fileURLToPath(new URL("..", import.meta.url)) }).trim();
const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
const errors = [];
let cardsOk = 0, chipsAll = 0, hashesAll = 0;
try {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  p.on("pageerror", (e) => errors.push(e.message));
  for (const idea of Object.keys(cards)) {
    await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await p.fill("#k-q", idea); await p.click("#k-go");
    await p.waitForSelector("#k-card > .k-card .k-schip", { timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(800);
    const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
      return { chips: [...(k?.querySelectorAll(".k-schip") || [])].map((a) => ({ src: a.dataset.src, href: a.href, h: a.getBoundingClientRect().height })),
        receipts: k?.querySelector("a[data-receipts]")?.href || "" }; });
    const id = (c.receipts.match(/receipts\/([0-9a-f]{16})/) || [])[1];
    const html = id ? await (await fetch(`${API}/receipts/${id}`)).text() : "";
    const rows = Object.fromEntries([...html.matchAll(/<tr id="([^"]+)" data-source="([^"]+)"/g)].map((m) => [m[1], m[2]]));
    const want = { qloo: "qloo", rule: "rule", model: "model", chain: "chain" };
    const opened = c.chips.filter((x) => { const row = new URL(x.href).hash.slice(1); return rows[row] === want[x.src] && x.h <= 16; });
    const doc = id ? await (await fetch(`${API}/api/receipts?id=${id}`)).json() : { rows: [] };
    let hashes = 0, good = 0;
    for (const r of doc.rows) {
      if (r.source === "qloo") { hashes++; good += sha(canon(r.call)) === r.hash; }
      if (r.id === "brief") { hashes++; good += ready(r.brief) === r.hash; }
    }
    const rec = doc.rows.find((r) => r.id === "record") || {};
    const fine = id && c.chips.length > 0 && opened.length === c.chips.length && hashes > 0 && good === hashes && rec.recorded && Number.isInteger(rec.seq);
    cardsOk += !!fine; chipsAll += c.chips.length; hashesAll += good;
    lines.push(`${fine ? "ok  " : "FAIL"} ${idea.slice(0, 40).padEnd(40)} ${opened.length} of ${c.chips.length} chips open their row (${[...new Set(c.chips.map((x) => x.src))].join(", ")}); ${good} of ${hashes} hashes recompute; record line ${rec.recorded ? rec.seq : `none (${rec.why})`}`);
    if (!fine) fails++;
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_receipts: ${cardsOk} of ${Object.keys(cards).length} cards; ${fails} check(s) failed`
  : `PASS test_receipts: on ${cardsOk} of ${Object.keys(cards).length} recorded cards every source chip (${chipsAll} in all) opens its receipt row and every hash recomputes (${hashesAll}); each record line has its sequence number`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
