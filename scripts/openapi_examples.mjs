// Sends each documented example of the app's OpenAPI document (GET /openapi.json) to the app, for every route marked
// x-read-only, and counts the 400s and 404s: a documented example that the server refuses or cannot find is a failure.
// A parameter whose example lives only while the server runs (x-example-from) is first read from the call it names; when
// that call has none today (no commitment yet), the route is listed as having no example now, which is not a failure.
//   node scripts/openapi_examples.mjs [base, default https://knos.onrender.com]   prints one line per route, then the counts
const BASE = process.argv[2] || "https://knos.onrender.com";
const doc = await (await fetch(`${BASE}/openapi.json`)).json();
const pick = (obj, path) => path.split(".").reduce((o, k) => (o == null ? undefined : o[/^\d+$/.test(k) ? Number(k) : k]), obj);
async function from(f) {
  const r = f.method === "POST" ? await fetch(BASE + f.path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f.body || {}) })
    : await fetch(BASE + f.path);
  return pick(await r.json().catch(() => ({})), f.pick);
}
const rows = [];
let sent = 0, failed = 0, none = 0;
for (const [path, ops] of Object.entries(doc.paths)) {
  for (const [method, op] of Object.entries(ops)) {
    if (!op["x-read-only"] || path.includes("{")) continue;
    const q = new URLSearchParams();
    let missing = null;
    for (const p of op.parameters || []) {
      if (p.in !== "query") continue;
      let v = p.example;
      if (p["x-example-from"]) v = await from(p["x-example-from"]);
      if (v === undefined && p["x-example-from"]) { missing = `no ${p.name} on this server now (${p["x-example-from"].path})`; break; }
      if (v === undefined && p.required) { missing = `no documented example for ${p.name}`; break; }
      if (v !== undefined) q.set(p.name, String(v));
    }
    if (missing) {
      const real = missing.startsWith("no documented");
      rows.push(`${real ? "FAIL" : "none"} ${method.toUpperCase()} ${path}: ${missing}`); real ? failed++ : none++;
      continue;
    }
    const body = method === "post" ? (() => { const c = op.requestBody?.content?.["application/json"] || {};
      return c.example ?? Object.values(c.examples || {})[0]?.value; })() : undefined;
    if (method === "post" && body === undefined) { rows.push(`FAIL POST ${path}: no documented body example`); failed++; continue; }
    const url = BASE + path + (q.toString() ? `?${q}` : "");
    const stop = new AbortController(), timer = setTimeout(() => stop.abort(), 30000);
    let code = 0;
    try {
      const r = await fetch(url, { method: method.toUpperCase(), redirect: "manual", signal: stop.signal,
        ...(body !== undefined ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
      code = r.status;
      stop.abort();                                     // the status is all that is read (an event stream never ends)
    } catch { /* aborted after the status, or no answer: code says which */ } finally { clearTimeout(timer); }
    sent++;
    const bad = code === 400 || code === 404 || code === 0;
    failed += bad;
    rows.push(`${bad ? "FAIL" : "ok  "} ${code} ${method.toUpperCase()} ${path}${q.toString() ? `?${q.toString().slice(0, 90)}` : ""}`);
  }
}
console.log(rows.join("\n"));
console.log(`${sent} documented examples sent to read-only routes: ${failed} failures (400, 404 or no answer); ${none} with no example on this server now`);
process.exit(failed ? 1 : 0);
