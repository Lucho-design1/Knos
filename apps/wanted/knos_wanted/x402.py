"""One paid route, priced per use over x402: GET /api/x402/report?hash=… costs 1 test unit on devnet.

First call answers HTTP 402 with an x402 challenge (scheme "exact", network solana-devnet, asset = this app's test
mint, payTo = the app's devnet test wallet's token account). The client signs a transfer of `maxAmountRequired` base units and sends
it base64 in the X-PAYMENT header ({"x402Version": 1, "scheme": "exact", "network": …, "payload": {"transaction": …}});
this server settles it on devnet (it is its own facilitator: sendTransaction, then confirmation) and serves the full
report with an X-PAYMENT-RESPONSE header. Devnet test money: the point is the mechanism, not revenue. An agent can pay
for a report the same way a person pre-orders: per use, no account.
"""
from __future__ import annotations

import base64
import binascii
import json

from . import escrow

PRICE_UNITS = 1
NETWORK = "solana-devnet"


class PaymentRequired(Exception):
    def __init__(self, challenge: dict):
        super().__init__("payment required")
        self.challenge = challenge


def ready() -> bool:
    try:
        return escrow.available() and bool(escrow.demo_key())
    except Exception:  # noqa: BLE001
        return False


def challenge(report_hash: str, base_url: str) -> dict:
    from knos.settle.v2 import pay
    led = escrow.ledger()
    mint = escrow.mint(led, create=True)
    to = pay.ata(escrow.demo_key().pubkey(), mint)
    return {"x402Version": 1, "error": "payment required",
            "accepts": [{"scheme": "exact", "network": NETWORK, "maxAmountRequired": str(PRICE_UNITS * escrow.UNIT),
                         "resource": f"{base_url}/api/x402/report?hash={report_hash}",
                         "description": f"The full Knos demand report {report_hash[:12]}… ({PRICE_UNITS} test unit; devnet test money)",
                         "mimeType": "application/json", "payTo": str(to), "asset": str(mint), "maxTimeoutSeconds": 60,
                         "extra": {"decimals": 6, "note": "test units of Knos's devnet test mint stand in for USDC"}}]}


def settle(header: str) -> dict:
    """The X-PAYMENT header -> the payment sent on devnet. Returns what X-PAYMENT-RESPONSE carries."""
    from knos import chain
    try:
        doc = json.loads(base64.b64decode(str(header or ""), validate=True))
    except (ValueError, binascii.Error):
        raise ValueError("X-PAYMENT: base64 JSON, as the x402 spec encodes it") from None
    if doc.get("x402Version") != 1 or doc.get("scheme") != "exact" or doc.get("network") != NETWORK:
        raise ValueError(f"X-PAYMENT: x402Version 1, scheme exact, network {NETWORK}")
    tx = (doc.get("payload") or {}).get("transaction")
    if not isinstance(tx, str) or not 100 < len(tx) < 4000:
        raise ValueError("X-PAYMENT.payload.transaction: the signed transfer, base64")
    led = escrow.ledger()
    sig = chain.call(led.url, "sendTransaction", [tx, {"encoding": "base64", "preflightCommitment": "confirmed"}], timeout=30)
    for _ in range(30):
        got = chain.call(led.url, "getSignatureStatuses", [[sig]], timeout=10)
        st = (got.get("value") or [None])[0]
        if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
            return {"success": True, "transaction": sig, "network": NETWORK, "payer": None,
                    "explorer": escrow.explorer(sig)}
        import time
        time.sleep(1)
    raise ValueError("the payment transaction was not confirmed in time")
