"""The x402 endpoint for graduation, pre-orders and paid checks (devnet test USDC), on the proposed "knos-order"
scheme of docs/reference/X402.md and the plumbing of knos.record_api (headers, limits, the socket): nothing forked.

    python -m knos.money.x402 --plans PLANS.json --offer OFFER.json [--port 8403]     (anyone runs it; Knos hosts none)

    GET /health             whether it answers; what it sells
    GET /fees               the fee schedule (config/fees.yaml, with each line's status), free
    GET /pool/<claim>       a graduated claim's pre-order pool as the chain has it now, free
    GET /preorder/<claim>   402 Payment Required: fund a pre-order in the claim's pool (a private knos_pay order in the
                            pool's scope). Asked again with PAYMENT-SIGNATURE naming the order: 200 "escrowed" once the
                            chain shows it open, in that pool, on those terms, in that mint, with time left.
    GET /checks             402: a pack of paid checks at the config's x402_check price (the smallest order is 5.00, so
                            one order buys a pack). Each call after that is signed by the wallet that funded the order
                            over "knos-check:<order>:<n>", n counting from 0; a replay or another wallet's call is refused.

The money never reaches this server: it sits in the order's own token account until the judge pays it, or goes back
to the payer after the deadline. `PAYMENT-RESPONSE` says "escrowed". Standard library at import; solders when a
payment is checked.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .. import record_api as ra
from . import fees_config

SCHEME, X402_VERSION, DEVNET = ra.SCHEME, ra.X402_VERSION, ra.DEVNET
ROUTES = ("/health", "/fees", "/pool/<claim>", "/preorder/<claim>", "/checks")
_CLAIM = re.compile(r"[A-Za-z0-9._-]{1,120}")
MARGIN = 3600                                            # a pre-order must have at least this long left (seconds), as record_api asks
NO_HOST = "Knos hosts no such server: whoever runs this one is its operator."


def check_message(order: str, n: int) -> bytes:
    return f"knos-check:{order}:{int(n)}".encode()


def pack(cfg: fees_config.FeeConfig) -> tuple[int, int]:
    """(checks in one pack, the pack's price): as many checks as the smallest order buys at the x402_check price."""
    from ..settle.v2 import pay
    each = fees_config.micro(cfg.doc["fees"]["x402_check"]["usd_each"])
    n = -(-pay.ORDER_MIN_AMOUNT // each)
    return n, n * each


class Server:
    """No socket: `handle(path, headers, client=, method=)` -> (status, headers, body). `plans`: {claim id: the plan
    knos.graduation.plan returned}; `offer`: what /checks sells, in knos.record_api.offer's shape (its amount is
    replaced by the pack's price); `mint`: the mint pre-orders are taken in; `chain`: infos, now, program_accounts.
    `state`: the JSON file that keeps how many checks each order has used, written before a paid call is answered, so a
    restart never sells a call twice; required with an offer."""

    def __init__(self, plans: dict[str, dict], chain, mint: str, offer: dict | None = None, cfg: fees_config.FeeConfig | None = None,
                 limiter: ra.Limiter | None = None, debug: bool = False, state: str | Path | None = None):
        self.cfg = cfg or fees_config.load()
        self.plans, self.chain, self.mint, self.debug = dict(plans), chain, mint, debug
        self.limiter = limiter or ra.Limiter()
        self.checks, price = pack(self.cfg)
        self.offer = {**offer, "amount": price, "price": price // self.checks, "lookups": self.checks} if offer else None
        if self.offer and state is None:
            raise ValueError("paid checks need a state file: the count of each order must survive a restart")
        self.state = Path(state) if state is not None else None
        self._used: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if self.state is None or not self.state.exists():
            return {}
        got = json.loads(self.state.read_text(encoding="utf-8"))
        if not isinstance(got, dict) or not all(isinstance(k, str) and isinstance(v, int) and v >= 0 for k, v in got.items()):
            raise ValueError(f"{self.state}: not a JSON object of order -> count")
        return got

    def _save(self) -> None:
        assert self.state is not None
        tmp = self.state.with_name(self.state.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._used, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state)

    # -- routes ------------------------------------------------------------------------------------------------------
    def handle(self, path: str, headers: dict[str, str], client: str = "", method: str = "GET") -> tuple[int, dict, dict]:
        h = {k.lower(): v for k, v in headers.items()}
        if method not in ("GET", "HEAD"):
            return 405, {"allow": "GET"}, {"error": "only GET"}
        wait = self.limiter.take(client or "-")
        if wait:
            return 429, {"retry-after": str(int(wait) + 1)}, {"error": "too many requests"}
        path = path.split("?", 1)[0]
        if len(path) > ra.MAX_PATH or not ra._PATH.fullmatch(path):
            return 400, {}, {"error": "a path is letters, digits and ./_- only"}
        try:
            if path == "/health":
                return 200, {}, {"ok": True, "routes": list(ROUTES), "claims": sorted(self.plans), "checks": bool(self.offer), "host": NO_HOST,
                                 "network": DEVNET, "revenue": "test money on devnet: 0"}
            if path == "/fees":
                return 200, {}, self.cfg.public()
            parts = path.strip("/").split("/")
            if len(parts) == 2 and parts[0] in ("pool", "preorder"):
                claim = parts[1]
                if not _CLAIM.fullmatch(claim) or claim not in self.plans:
                    return 404, {}, {"error": f"no graduated claim {claim!r} on this server"}
                p = self.plans[claim]
                if parts[0] == "pool":
                    from .. import graduation
                    return 200, {}, {"claim": claim, "pool": graduation.pool(self.chain, p, self.mint), "spec_hash": p["spec_hash"]}
                return self._preorder(claim, p, h, path)
            if path == "/checks" and self.offer:
                return self._checks(h, path)
        except ra.Bad as why:
            return 400, {}, {"error": str(why)}
        return 404, {}, {"error": "no such route"}

    # -- pre-orders ------------------------------------------------------------------------------------------------------
    def requirement(self, claim: str, p: dict, payer: str | None) -> dict:
        from solders.pubkey import Pubkey
        from .. import graduation
        from ..settle.v2 import pay
        amount = pay.ORDER_MIN_AMOUNT
        return {"scheme": SCHEME, "network": DEVNET, "amount": str(amount), "asset": self.mint, "payTo": None,
                "maxTimeoutSeconds": p["pool"]["work_s"],
                "extra": {"program": p["program"], "order": str(graduation.address(p, "pool", Pubkey.from_string(payer))) if payer else None,
                          "private": True, "scope": p["pool"]["scope"], "options": p["options"], "repoId": "0", "issue": "0", "seq": 0,
                          "mode": p["mode"], "terms": p["pool"]["terms"], "termsHash": p["pool"]["terms_hash"],
                          "workflows": {"repository": p["wf_repo"], "sha": p["wf_sha"]}, "judgeRepoId": str(p["repo_id"]),
                          "fee": str(self.cfg.fee("payout", amount)), "minAmount": str(amount), "claim": claim, "specHash": p["spec_hash"],
                          "payees": [list(x) for x in p["payees"]], "refund": "after-deadline"}}

    def _required(self, accepts: list, error: str, resource: str, what: str) -> tuple[int, dict, dict]:
        body = {"x402Version": X402_VERSION, "error": error, "resource": {"url": resource, "description": what, "mimeType": "application/json"},
                "accepts": accepts, "extensions": {SCHEME: {"info": {"version": 1, "proposal": True, "settles": "on-acceptance",
                                                                     "refund": "after-deadline", "payerHeader": "Attested-Payer"}}}}
        return 402, {"payment-required": ra.encode(body)}, body

    def _payer(self, h: dict) -> str | None:
        payer = h.get(ra.PAYER_HEADER)
        if payer is not None and not ra.address(payer):
            raise ra.Bad("the Attested-Payer header is not a Solana address")
        return payer

    def _payment(self, h: dict) -> tuple[dict, str]:
        raw = h.get("payment-signature", "")
        if len(raw) > ra.MAX_HEADER:
            raise ra.Bad(f"the PAYMENT-SIGNATURE header is over {ra.MAX_HEADER} characters")
        try:
            got = ra.decode(raw)
        except (ValueError, TypeError):
            raise ra.Bad("the PAYMENT-SIGNATURE header is not base64 JSON") from None
        if not isinstance(got, dict) or not isinstance(got.get("payload"), dict) or not ra.address(got["payload"].get("order")):
            raise ra.Bad("the PAYMENT-SIGNATURE header needs payload.order, the order's address")
        return got, got["payload"]["order"]

    def _preorder(self, claim: str, p: dict, h: dict, resource: str) -> tuple[int, dict, dict]:
        if "payment-signature" not in h:
            return self._required([self.requirement(claim, p, self._payer(h))], "PAYMENT-SIGNATURE header is required", resource,
                                  f"a pre-order of graduated claim {claim}: held by knos_pay, paid to its makers on accepted delivery, refunded after the deadline")
        _, order = self._payment(h)
        o, why = self.verify_pool_order(p, order)
        if o is None:
            return self._required([self.requirement(claim, p, None)], why, resource, f"a pre-order of graduated claim {claim}")
        resp = {"success": True, "network": DEVNET, "transaction": "", "payer": str(o.source), "status": "escrowed", "order": order}
        return 200, {"payment-response": ra.encode(resp)}, {"escrowed": True, "claim": claim, "order": order, "amount": o.amount, "fee": o.fee,
                                                           "deadline": o.deadline, "said": "Held by knos_pay: paid to the makers on accepted delivery, "
                                                                                           "refunded with its fee after the deadline."}

    def verify_pool_order(self, p: dict, order: str) -> tuple[Any, str | None]:
        """The order a pre-order payment names: knos_pay's, in this claim's pool, open, on its terms, in the mint,
        with time left. (order, None) or (None, why)."""
        from solders.pubkey import Pubkey
        from ..settle.v2 import pay
        got = self.chain.infos([Pubkey.from_string(order)])[0]
        if got is None:
            return None, f"there is no order at {order}: fund it first (FundOrderWallet), or it was paid or refunded"
        if str(got[0]) != p["program"]:
            return None, f"{order} is not an account of {p['program']}"
        o = pay.read_order(bytes(got[1]))
        if o is None:
            return None, f"{order} is not a work order"
        if o.scope.hex() != p["pool"]["scope"] or pay.order_pda(o.scope, o.source, o.seq, Pubkey.from_string(p["program"])) != Pubkey.from_string(order):
            return None, "the order is not in this claim's pre-order pool"
        if o.state != "open":
            return None, "the order is not open"
        from .. import graduation
        why = graduation.mismatch(p, "pool", o, self.mint)     # terms, mode, judge, pinned workflows, flags, mint
        if why is not None:
            return None, f"the order is not one of this pool's: {why}"
        if o.deadline < self.chain.now() + MARGIN:
            return None, "the order's deadline leaves too little time"
        return o, None

    # -- paid checks ---------------------------------------------------------------------------------------------------
    def _checks(self, h: dict, resource: str) -> tuple[int, dict, dict]:
        off = self.offer
        assert off is not None
        if "payment-signature" not in h:
            req = ra.requirement(off, self._payer(h))
            req["extra"].pop("record", None)
            req["extra"]["checks"] = {"price": str(off["price"]), "count": self.checks, "sign": "knos-check:<order>:<n>"}
            return self._required([req], "PAYMENT-SIGNATURE header is required", resource,
                                  f"a pack of {self.checks} paid checks at {off['price'] / 1e6:g} test USDC each")
        got, order = self._payment(h)
        n, sig = got["payload"].get("n"), got["payload"].get("signature")
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or not isinstance(sig, str):
            raise ra.Bad("payload.n (the call's number on the order, from 0) and payload.signature are needed")
        o, why = ra.verify(self.chain, off, order)
        if o is None:
            return 402, {}, {"error": why}
        from solders.pubkey import Pubkey
        from solders.signature import Signature
        try:
            ok = Signature.from_string(sig).verify(Pubkey.from_string(str(o.source)), check_message(order, n))
        except ValueError:
            ok = False
        if not ok:
            return 401, {}, {"error": "the call is not signed by the wallet that funded the order"}
        used = self._used.get(order, 0)
        if n != used:
            return 409, {}, {"error": f"call {n} on this order: the next is {used} (a replay, or one skipped)"}
        if used >= self.checks:
            return 402, {}, {"error": f"the order's {self.checks} checks are used: fund another"}
        self._used[order] = used + 1
        self._save()                    # kept before the answer: a restart never sells this call again
        resp = {"success": True, "network": DEVNET, "transaction": "", "payer": str(o.source), "status": "escrowed", "order": order}
        return 200, {"payment-response": ra.encode(resp)}, {"paid": True, "order": order, "n": n, "left": self.checks - used - 1,
                                                           "run": "knos verify runs the check; this endpoint meters it"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos.money.x402", description="The x402 endpoint for graduation pre-orders and paid checks (devnet).")
    ap.add_argument("--plans", type=Path, required=True, help="JSON: {claim id: plan} (or a revenue_devnet.json, whose claims are read)")
    ap.add_argument("--mint", required=True, help="the mint pre-orders are taken in")
    ap.add_argument("--offer", type=Path, help="JSON in knos.record_api.offer's shape: what /checks sells")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8403)
    ap.add_argument("--state", type=Path, default=Path.home() / ".knos" / "x402_checks.json", help="where the count of each order's paid checks is kept")
    a = ap.parse_args(argv)
    doc = json.loads(a.plans.read_text(encoding="utf-8"))
    plans = {c["plan"]["claim_id"]: c["plan"] for c in doc["claims"].values()} if "claims" in doc else doc
    from .. import chain
    server = Server(plans, chain.ledger(), a.mint, json.loads(a.offer.read_text(encoding="utf-8")) if a.offer else None,
                    state=a.state)
    http = ra.serve(server, a.host, a.port)     # type: ignore[arg-type] - the same handle(path, headers, client=, method=)
    print(f"knos money x402 on http://{a.host}:{a.port} ({', '.join(ROUTES)})", file=sys.stderr)
    http.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
