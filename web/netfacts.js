// #network "network facts": what Solana devnet says about itself, read in this browser when the section comes near the
// screen (web/app.js later()). Every value is an RPC answer as it came; a method this RPC refuses is said so, never
// guessed. A 429 is retried with backoff (1 s, 2 s, 4 s, 8 s).
// Live, over the cluster's WebSocket (no polling): slotSubscribe + rootSubscribe (the finality clock) and logsSubscribe
// on Knos's two programs (an activity feed). The genesis hash is checked first: an endpoint that is not devnet is refused.
const DEVNET = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
export const ENDPOINTS = ["https://api.devnet.solana.com"];
export const WSS = "wss://api.devnet.solana.com";
const FEATURE = "Feature111111111111111111111111111111111111";
const MEMO = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";
const TEST_MINT = "5XJJTDxBF1LqbQ9MAURyYUnHCPcd4JHxjdy9or2gWjsX";   // the lab escrow's test-unit mint (labs_devnet.json)
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const num = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : String(n));

let id = 0;
/** One JSON-RPC call: 429 -> backoff and retry; any other failure -> {error}. */
export async function rpc(method, params = [], url = ENDPOINTS[0], fetcher = globalThis.fetch) {
  for (let i = 0; i < 4; i++) {
    let r;
    try {
      r = await fetcher(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: ++id, method, params }) });
    } catch (e) { return { error: `unreachable (${e.message})` }; }
    if (r.status === 429) { await sleep(1000 * 2 ** i); continue; }
    const j = await r.json().catch(() => ({ error: { message: `HTTP ${r.status}` } }));
    return j.error ? { error: j.error.message || String(j.error.code) } : { result: j.result };
  }
  return { error: "rate limited (429) after 4 tries" };
}

const ALPHA = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
export function b58decode(s) {
  let n = 0n;
  for (const c of s) n = n * 58n + BigInt(ALPHA.indexOf(c));
  const out = [];
  while (n > 0n) { out.unshift(Number(n % 256n)); n /= 256n; }
  for (const c of s) { if (c !== "1") break; out.unshift(0); }
  return Uint8Array.from(out);
}
/** A legacy message of one Memo instruction paid by `payer`: what getFeeForMessage prices before anyone signs. */
export function memoMessage(payer, blockhash, text = "knos fee preview") {
  const data = new TextEncoder().encode(text);
  const parts = [Uint8Array.of(1, 0, 1, 2), b58decode(payer), b58decode(MEMO), b58decode(blockhash), Uint8Array.of(1, 1, 1, 0, data.length), data];
  const out = new Uint8Array(parts.reduce((a, p) => a + p.length, 0));
  let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
  return btoa(String.fromCharCode(...out));
}

/** The facts, as rows of [name, value, method]. `payer`: any address (the fee preview's payer). */
export async function facts(payer, call = rpc) {
  const g = await call("getGenesisHash");
  if (g.result && g.result !== DEVNET) return [["cluster", `refused: genesis ${g.result} is not devnet`, "getGenesisHash"]];
  const bh = await call("getLatestBlockhash", [{ commitment: "finalized" }]);
  const hash = bh.result?.value?.blockhash;
  const asks = [
    ["health", "getHealth", [], (r) => r],
    ["node version", "getVersion", [], (r) => r["solana-core"]],
    ["epoch", "getEpochInfo", [{ commitment: "finalized" }], (r) => `${num(r.epoch)}, slot ${num(r.slotIndex)} of ${num(r.slotsInEpoch)}`],
    ["epoch length", "getEpochSchedule", [], (r) => `${num(r.slotsPerEpoch)} slots`],
    ["finalized slot", "getSlot", [{ commitment: "finalized" }], (r) => num(r)],
    ["block height", "getBlockHeight", [{ commitment: "finalized" }], (r) => num(r)],
    ["slots per second (last sample)", "getRecentPerformanceSamples", [1], (r) => r[0] ? (r[0].numSlots / r[0].samplePeriodSecs).toFixed(2) : "none"],
    ["transactions per second", "getRecentPerformanceSamples", [1], (r) => r[0] ? Math.round(r[0].numTransactions / r[0].samplePeriodSecs) : "none"],
    ["cluster nodes", "getClusterNodes", [], (r) => num(r.length)],
    ["vote accounts (current / delinquent)", "getVoteAccounts", [], (r) => `${num(r.current.length)} / ${num(r.delinquent.length)}`],
    ["supply (SOL, circulating)", "getSupply", [{ excludeNonCirculatingAccountsList: true }], (r) => num(Math.round(r.value.circulating / 1e9))],
    ["inflation rate (total)", "getInflationRate", [], (r) => `${(r.total * 100).toFixed(2)}% (epoch ${r.epoch})`],
    ["stake minimum delegation (SOL)", "getStakeMinimumDelegation", [], (r) => (r.value / 1e9).toString()],
    ["priority fee (median of recent, micro-lamports/CU)", "getRecentPrioritizationFees", [], (r) => {
      const f = r.map((x) => x.prioritizationFee).sort((a, b) => a - b); return f.length ? num(f[Math.floor(f.length / 2)]) : "none"; }],
    ["rent for a token account (SOL)", "getMinimumBalanceForRentExemption", [165], (r) => (r / 1e9).toFixed(6)],
    ["largest accounts", "getLargestAccounts", [{ filter: "circulating" }], (r) => `${num(r.value.length)} listed`],
    ["block time of the finalized slot", "getBlockTime", null, (r) => new Date(r * 1000).toISOString().slice(11, 19) + " UTC"],
    ["leader of the next slots", "getSlotLeaders", null, (r) => `${r.length} leaders listed`],
  ];
  const slot = (await call("getSlot", [{ commitment: "finalized" }])).result;
  const rows = [["genesis hash", g.result === DEVNET ? "devnet" : g.error || "?", "getGenesisHash"]];
  const got = await Promise.all(asks.map(([name, m, p, f]) => call(m, p ?? (m === "getBlockTime" ? [slot] : [slot, 5])).then((r) => [name, r.error ? `not answered here: ${r.error}` : f(r.result), m])));
  rows.push(...got);
  // one validator's share: its leader slots this epoch, its vote account's last inflation reward
  const v0 = (await call("getVoteAccounts", [])).result?.current?.[0];
  if (v0) {
    const ls = await call("getLeaderSchedule", [null, { identity: v0.nodePubkey }]);
    rows.push(["leader slots this epoch (one validator)", ls.error ? `not answered here: ${ls.error}` : num((ls.result?.[v0.nodePubkey] || []).length), "getLeaderSchedule"]);
    const ir = await call("getInflationReward", [[v0.votePubkey]]);
    rows.push(["last inflation reward (one vote account, SOL)", ir.error ? `not answered here: ${ir.error}` : ir.result?.[0] ? (ir.result[0].amount / 1e9).toFixed(4) : "none", "getInflationReward"]);
  }
  const tl = await call("getTokenLargestAccounts", [TEST_MINT]);
  rows.push(["largest holders of the Knos test units", tl.error ? `not answered here: ${tl.error}` : `${num(tl.result?.value?.length ?? 0)} listed`, "getTokenLargestAccounts"]);
  if (hash) {
    const v = await call("isBlockhashValid", [hash, { commitment: "processed" }]);
    rows.push(["latest blockhash valid", v.error ? `not answered: ${v.error}` : String(v.result.value), "isBlockhashValid"]);
    const fee = await call("getFeeForMessage", [memoMessage(payer, hash), { commitment: "processed" }]);
    rows.push(["fee for a one-memo transaction (lamports)", fee.error ? `not answered: ${fee.error}` : num(fee.result.value), "getFeeForMessage"]);
  }
  const ft = await call("getProgramAccounts", [FEATURE, { encoding: "base64", dataSlice: { offset: 0, length: 1 } }]);
  rows.push(["active features (feature gate)", ft.error ? `not answered here: ${ft.error}` : `${num(ft.result.filter((a) => atob(a.account.data[0]).charCodeAt(0) === 1).length)} of ${num(ft.result.length)}`, "getProgramAccounts"]);
  return rows;
}

export function factsHtml(rows) {
  return `<h3>Network facts, read from devnet now</h3><div class="k-table"><table id="netfacts"><tbody>${rows.map(([n, v, m]) =>
    `<tr><td>${esc(n)}</td><td class="k-num">${esc(v)}</td><td class="mono small">${esc(m)}</td></tr>`).join("")}</tbody></table></div>
    <p class="fine" id="finality-clock" aria-live="polite">Finality clock: connecting…</p><ol class="small" id="activity-feed" aria-label="Knos programs, live"></ol>`;
}

/** Live over the WebSocket: the processed and rooted (finalized) slots, and the logs of `programs`. Returns stop(). */
export function live(el, programs, WS = globalThis.WebSocket) {
  if (!WS) return () => {};
  const ws = new WS(WSS);
  let slot = 0, root = 0, blocks = 0, updates = 0;
  const streams = {};
  const clock = el.querySelector("#finality-clock"), feed = el.querySelector("#activity-feed");
  ws.onopen = () => {
    ws.send(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "slotSubscribe" }));
    ws.send(JSON.stringify({ jsonrpc: "2.0", id: 2, method: "rootSubscribe" }));
    programs.forEach((p, i) => ws.send(JSON.stringify({ jsonrpc: "2.0", id: 3 + i, method: "logsSubscribe", params: [{ mentions: [p] }, { commitment: "finalized" }] })));
    // a new or changed escrow account of the first program, pushed as it happens (the data itself is not needed here)
    // block and slot-update streams: asked for, and the clock says when this RPC does not offer them
    ws.send(JSON.stringify({ jsonrpc: "2.0", id: 10, method: "blockSubscribe", params: ["all", { commitment: "finalized", transactionDetails: "none", rewards: false }] }));
    ws.send(JSON.stringify({ jsonrpc: "2.0", id: 11, method: "slotsUpdatesSubscribe" }));
    if (programs[0]) ws.send(JSON.stringify({ jsonrpc: "2.0", id: 9, method: "programSubscribe", params: [programs[0], { commitment: "confirmed", encoding: "base64", dataSlice: { offset: 0, length: 0 } }] }));
  };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === "slotNotification") slot = m.params.result.slot;
    if (m.method === "rootNotification") root = m.params.result;
    if (m.method === "logsNotification" && feed) {
      const v = m.params.result.value;
      feed.insertAdjacentHTML("afterbegin", `<li><a class="mono" href="https://explorer.solana.com/tx/${esc(v.signature)}?cluster=devnet" rel="noopener">${esc(v.signature.slice(0, 10))}…</a> ${v.err ? "failed" : "finalized"}</li>`);
      while (feed.children.length > 8) feed.lastChild.remove();
    }
    if (m.method === "programNotification" && feed) {
      const k = m.params.result.value.pubkey;
      feed.insertAdjacentHTML("afterbegin", `<li>escrow account <a class="mono" href="https://explorer.solana.com/address/${esc(k)}?cluster=devnet" rel="noopener">${esc(k.slice(0, 10))}…</a> changed</li>`);
      while (feed.children.length > 8) feed.lastChild.remove();
    }
    if (m.method === "blockNotification") blocks++;
    if (m.method === "slotsUpdatesNotification") updates++;
    if ((m.id === 10 || m.id === 11) && m.error) streams[m.id] = "not offered by this RPC";
    if (clock && slot && root) clock.textContent = `Finality clock: slot ${num(slot)}, finalized ${num(root)} (${num(slot - root)} behind); `
      + `blocks ${streams[10] || num(blocks)}, slot updates ${streams[11] || num(updates)}`;
  };
  ws.onerror = () => { if (clock) clock.textContent = "Finality clock: the WebSocket did not connect here."; };
  return () => ws.close();
}
