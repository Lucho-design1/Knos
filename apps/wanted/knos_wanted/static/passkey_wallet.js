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
    // a pre-order: the one inner instruction is knos_pay's FundOrderWallet (tag 15) for the amount shown
    if (step.kind === "preorder") {
      const sp = hex(p.signed_payload); const n = sp[0]; let at = 1;
      if (n !== 1) throw new Error("a pre-order signs exactly one instruction");
      const prog = p.accounts[sp[at]]; const na = sp[at + 1]; at += 2 + na;
      const len = sp[at] | (sp[at + 1] << 8); const data = sp.slice(at + 2, at + 2 + len);
      const amount = Number(new DataView(data.buffer, data.byteOffset + 17, 8).getBigUint64(0, true)) / 1e6;
      if (prog !== step.summary.program || data[0] !== 15 || Math.abs(amount - step.summary.amount_units) > 1e-9)
        throw new Error("the pre-order to sign is not the one shown: nothing was signed");
    }
  }

  async function approve(step, api) {
    for (let i = 0; i < 3; i++) {
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
