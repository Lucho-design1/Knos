// The revenue dashboard (web/revenue/index.html). It draws revenue_data.json, which `python -m knos.money.revenue`
// writes from config/fees.yaml and a read of devnet. `model` is knos.money.revenue.model, line for line
// (tests/test_money_revenue.py runs both on the same inputs when node is installed). textContent only: no HTML is built
// from data.

const MICRO = 1_000_000;
const usd = (x) => Number(x || 0);
const money = (n) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const round2 = (n) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);

export const INPUTS = [
  ["verifications", "Hosted verifications a month"],
  ["payout_volume_usd", "Value released from escrow a month (USD)"],
  ["payouts", "Releases a month"],
  ["graduation_volume_usd", "Value released after graduation a month (USD)"],
  ["task_package_sales_usd", "Task package sales a month (USD)"],
];

export function model(inputs, schedule) {
  const f = schedule.fees, x = inputs || {};
  const month = {};
  month.verification = Math.max(0, usd(x.verifications) - usd(f.verification.free_per_month)) * usd(f.verification.usd_each);
  month.payout = Math.max(usd(x.payout_volume_usd) * f.payout.rate_bps / 10000, usd(x.payouts) * usd(f.payout.floor_usd));
  month.graduation = usd(x.graduation_volume_usd) * f.graduation.rate_bps / 10000;
  month.task_package = usd(x.task_package_sales_usd) * f.task_package.knos_bps / 10000;
  const subs = x.cloud_subscribers || {};
  month.cloud = schedule.cloud.tiers.reduce((s, t) => s + usd(t.usd_month) * usd(subs[t.name]), 0);
  const out = {};
  for (const k of Object.keys(month)) out[k] = round2(month[k]);
  const total = Object.values(month).reduce((a, b) => a + b, 0);
  return { month: out, month_total: round2(total) };
}

function el(doc, tag, text, cls) {
  const e = doc.createElement(tag);
  if (text !== undefined) e.textContent = String(text);
  if (cls) e.className = cls;
  return e;
}

function row(doc, cells) {
  const tr = doc.createElement("tr");
  for (const c of cells) {
    const td = el(doc, "td", c && c.text !== undefined ? c.text : c, c && c.cls);
    if (c && c.tag) { td.textContent = ""; td.appendChild(el(doc, "span", c.tag, "tag " + c.tag)); }
    tr.appendChild(td);
  }
  return tr;
}

function rate(line) {
  if (line.rate_bps !== undefined) return `${line.rate_bps / 100}%` + (line.floor_usd ? `, at least ${line.floor_usd}` : "");
  if (line.knos_bps !== undefined) return `${line.knos_bps / 100}% to Knos, the rest to the maintainer`;
  if (line.usd_each !== undefined) return `${line.usd_each} USD each` + (line.free_per_month ? `, ${Number(line.free_per_month).toLocaleString("en-US")} a month free; public repositories free` : "");
  return "";
}

export function renderRevenue(doc, d) {
  const $ = (id) => doc.getElementById(id);
  const s = d.schedule;
  $("rev-real").textContent = `Revenue: ${d.revenue.usd} USD`;
  $("rev-why").textContent = d.revenue.why;
  $("rev-generated").textContent = `Data written ${d.generated} (UTC). Treasury ${d.treasury.read ? "read from devnet then" : "not read: shown as unknown"}.`;
  const tb = $("rev-treasury").querySelector("tbody");
  for (const a of d.treasury.accounts) tb.appendChild(row(doc, [a.label, { text: a.address }, { text: a.balance === null ? "not read" : money(a.balance / MICRO), cls: "num" }]));
  const g = d.graduation_demo;
  if (g) {
    $("rev-demo").textContent = `Synthetic claim A: ${money(usd(g.escrow_locked) / MICRO)} test units in the milestone escrow and ${money(usd(g.pool_locked) / MICRO)} pre-ordered by ${g.pool_buyers} buyers, read ${g.read}. Program ${g.program}, the demo's own test mint ${g.mint}.`;
    for (const sg of g.signatures) {
      const li = el(doc, "li", sg.step + ": ");
      const a = el(doc, "a", sg.signature.slice(0, 16) + "…");
      a.href = sg.explorer; a.rel = "noopener";
      li.appendChild(a);
      $("rev-sigs").appendChild(li);
    }
  } else {
    $("rev-demo").textContent = "No graduation demo has run.";
  }
  const fb = $("rev-fees").querySelector("tbody");
  for (const [k, line] of Object.entries(s.fees)) fb.appendChild(row(doc, [k.replace("_", " "), line.what, rate(line), { tag: line.status }]));
  const sb = $("rev-split").querySelector("tbody");
  for (const [r, b] of Object.entries(s.splits.roles)) sb.appendChild(row(doc, [r, { text: `${b / 100}%`, cls: "num" }]));
  sb.appendChild(row(doc, ["status", { tag: s.splits.status }]));
  const cb = $("rev-cloud").querySelector("tbody");
  for (const t of s.cloud.tiers) cb.appendChild(row(doc, [t.name, { text: t.usd_month, cls: "num" }, { text: Number(t.credits_month).toLocaleString("en-US"), cls: "num" }, { tag: s.cloud.status }]));
  $("rev-cloud-shape").textContent = s.cloud.shape_from;

  const form = $("rev-inputs");
  const values = { cloud_subscribers: {} };
  const draw = () => {
    const m = model(values, s);
    const ob = $("rev-out").querySelector("tbody");
    ob.textContent = "";
    const st = { verification: s.fees.verification.status, payout: s.fees.payout.status, graduation: s.fees.graduation.status, task_package: s.fees.task_package.status, cloud: s.cloud.status };
    for (const [k, v] of Object.entries(m.month)) ob.appendChild(row(doc, [k.replace("_", " "), { text: money(Number(v)), cls: "num" }, { tag: st[k] }]));
    ob.appendChild(row(doc, ["total (MODEL)", { text: money(Number(m.month_total)), cls: "num" }, ""]));
  };
  const field = (key, label, set) => {
    const l = el(doc, "label", label + " ");
    const i = doc.createElement("input");
    i.type = "number"; i.min = "0"; i.value = "0"; i.inputMode = "numeric";
    i.addEventListener("input", () => { set(Math.max(0, Number(i.value) || 0)); draw(); });
    l.appendChild(i); form.appendChild(l);
  };
  for (const [k, label] of INPUTS) { values[k] = 0; field(k, label, (v) => { values[k] = v; }); }
  for (const t of s.cloud.tiers) { values.cloud_subscribers[t.name] = 0; field(t.name, `${t.name} subscribers`, (v) => { values.cloud_subscribers[t.name] = v; }); }
  draw();

  const b = d.one_billion;
  $("rev-target-label").textContent = b.label;
  const items = [
    [`Released from escrow a year at the payout rate`, b.payout_volume_usd_year, "USD"],
    [`Hosted verifications a year at the verification price`, b.verifications_year, "verifications"],
    [`Value released after graduation a year at the graduation rate (placeholder)`, b.graduation_volume_usd_year, "USD"],
    [`Task package sales a year at Knos's share (placeholder)`, b.task_package_sales_usd_year, "USD"],
    [`Subscribers to the ${b.cloud_top_tier} tier for a year (placeholder price)`, b.cloud_subscribers_at_top_tier, ""],
  ];
  for (const [what, n, unit] of items) if (n !== undefined) $("rev-target").appendChild(el(doc, "li", `${what}: ${Number(n).toLocaleString("en-US")} ${unit}`.trim()));
  for (const src of Object.values(s.sources)) $("rev-sources").appendChild(el(doc, "li", `${src.said}. Source: ${src.source}. Not audited.`));
}
