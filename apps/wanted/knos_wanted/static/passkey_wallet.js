// Knos: your passkey approves every payment. The server returns a step {intent, challenge, parts, summary}; this file
// recomputes the challenge from the parts itself (so the passkey signs only what the summary says), asks the passkey
// (navigator.credentials.get), and posts the answer to /api/sign, which relays it to Solana devnet. The secp256r1
// precompile checks the signature; LazorKit (the wallet program) checks it covers exactly these instructions.
"use strict";
(function () {
  const hex = (h) => Uint8Array.from((h.match(/../g) || []).map((x) => parseInt(x, 16)));
  const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  function b58(s) {
    let n = [0];
    for (const ch of s) {
      let c = B58.indexOf(ch); if (c < 0) throw new Error("bad address");
      for (let i = 0; i < n.length; i++) { c += n[i] * 58; n[i] = c & 255; c >>= 8; }
      while (c) { n.push(c & 255); c >>= 8; }
    }
    for (const ch of s) { if (ch === "1") n.push(0); else break; }
    const out = new Uint8Array(32); const r = n.reverse(); out.set(r.slice(-32), 32 - Math.min(32, r.length)); return out;
  }
  const le = (v, n) => { const o = new Uint8Array(n); let x = BigInt(v); for (let i = 0; i < n; i++) { o[i] = Number(x & 255n); x >>= 8n; } return o; };
  const cat = (...a) => { const o = new Uint8Array(a.reduce((s, x) => s + x.length, 0)); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };
  const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64u = (s) => { s = s.replace(/-/g, "+").replace(/_/g, "/"); const b = atob(s + "===".slice((s.length + 3) % 4)); return Uint8Array.from(b, (c) => c.charCodeAt(0)); };

  // What the passkey is about to sign, rebuilt here: sha256(discriminator || auth payload || signed payload || slot ||
  // payer || counter || program), as LazorKit's program computes it.
  async function check(step) {
    const p = step.parts;
    const raw = cat(new Uint8Array([p.discriminator]), hex(p.auth_payload), hex(p.signed_payload), le(p.slot, 8), b58(p.payer), le(p.counter, 4), b58(p.program));
    const got = b64u(await crypto.subtle.digest("SHA-256", raw));
    if (got !== step.challenge) throw new Error("the step the server returned does not match its challenge: nothing was signed");
    // a pre-order or a milestone's funding: the one inner instruction is knos_pay's FundOrderWallet (tag 15) for the
    // amount shown; a commitment to buy (AMC): the one inner instruction is the token program's Approve (4) of it
    const one = () => {
      const sp = hex(p.signed_payload); let at = 1;
      if (sp[0] !== 1) throw new Error("this step signs exactly one instruction");
      const prog = p.accounts[sp[at]]; const na = sp[at + 1]; at += 2 + na;
      const len = sp[at] | (sp[at + 1] << 8); return { prog, data: sp.slice(at + 2, at + 2 + len) };
    };
    const units = (data, at) => Number(new DataView(data.buffer, data.byteOffset + at, 8).getBigUint64(0, true)) / 1e6;
    if (step.kind === "preorder" || step.kind === "project_fund") {
      const { prog, data } = one();
      if (prog !== step.summary.program || data[0] !== 15 || Math.abs(units(data, 17) - step.summary.amount_units) > 1e-9)
        throw new Error("the payment to sign is not the one shown: nothing was signed");
    }
    if (step.kind === "amc") {
      const { prog, data } = one();
      if (prog !== "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA" || data[0] !== 4 || Math.abs(units(data, 1) - step.summary.allowance_units) > 1e-9)
        throw new Error("the commitment to sign is not the one shown: nothing was signed");
    }
  }

  // the approval card: what this step does, in plain words, before the passkey is asked (the passkey then signs exactly that)
  function card(s) {
    return new Promise((ok, no) => {
      const f = s.network_fee, el = document.createElement("div");
      el.className = "ux-sheet"; el.id = "pk-card"; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "Approve this step");
      const rows = [["What", s.what], ["Amount", s.amount_units != null ? `${s.amount_units} test units` : s.allowance_units != null ? `${s.allowance_units} test units (allowance)` : null],
        ["Fee", s.fee_units != null ? `${s.fee_units} test units` : null], ["Network fee", f ? `${f.lamports.toLocaleString()} lamports, paid by ${f.paid_by}` : null],
        ["If it fails", s.refunded_to ? "refunded to your wallet" : null], ["Money", s.money]].filter((r) => r[1]);
      el.innerHTML = `<p class="small"><strong>Approve with your passkey</strong></p>` + rows.map(([k, v]) => `<p class="small"><span class="muted">${k}:</span> ${String(v).replace(/[<>&]/g, "")}</p>`).join("") +
        `<div class="row"><button type="button" id="pk-approve">Approve</button><button type="button" class="quiet" id="pk-cancel">Cancel</button></div>`;
      document.body.appendChild(el);
      el.querySelector("#pk-approve").onclick = () => { el.remove(); ok(); };
      el.querySelector("#pk-cancel").onclick = () => { el.remove(); no(new Error("cancelled: nothing was signed")); };
      el.querySelector("#pk-approve").focus();
    });
  }
  async function approve(step, api) {
    await card(step.summary || {});
    // Chrome may add a key to the client data at random ("other_keys_can_be_added_here"), so an answer can differ from
    // the prediction more than once in a row: each round learns what the authenticator said and asks again
    for (let i = 0; i < 5; i++) {
      await check(step);
      const a = await navigator.credentials.get({ publicKey: { challenge: unb64u(step.challenge), rpId: step.rp_id, timeout: 60000,
        userVerification: "preferred", allowCredentials: [{ type: "public-key", id: unb64u(step.credential) }] } });
      const got = await api("/api/sign", { intent: step.intent, authenticatorData: b64u(a.response.authenticatorData),
        clientDataJSON: b64u(a.response.clientDataJSON), signature: b64u(a.response.signature) });
      if (!got.again) return got;
      step = got;                      // the authenticator answered with other flags or count: one more touch
    }
    throw new Error("the passkey's answers did not settle; try again");
  }
  window.KnosPasskey = { approve, check };
})();
