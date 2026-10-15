"""Pay a lab's invoice over x402 on whichever chain the lab names: USDC on Base (testnet: Base Sepolia) or on Solana
(devnet). Chain-agnostic: the lab's 402 challenge says the network, asset, amount and payee; Knos never hard-codes them.

    challenge = decode_challenge(headers, body)        PAYMENT-REQUIRED header (x402 v2, base64 JSON), or a v1 body
    req = choose(challenge["accepts"], networks)       the first requirement on a network Knos can pay
    payload = evm_payload(req, key, ...)               x402 `exact` on EVM: an EIP-3009 TransferWithAuthorization,
                                                       EIP-712 signed (knos.labs.evm); the facilitator pays the gas
    payload = solana_payload(req, keypair, ...)        x402 `exact` on Solana (knos.money.x402_exact)
    header = encode(payload)                           the PAYMENT-SIGNATURE header to retry with
    check_evm(payload, req, now)                       why a facilitator would refuse it ([] when it would not on
                                                       signature, payee, amount, asset, network and time grounds)

Sources read 14 Oct 2026: the x402 `exact` EVM scheme (github.com/coinbase/x402 specs/schemes/exact/scheme_exact_evm.md:
PaymentPayload with `accepted` and `payload.{signature, authorization}`, Base Sepolia USDC
0x036CbD53842c5426634e7929541eC2318f3dCF7e, extra {assetTransferMethod eip3009, name, version}); the public testnet
facilitator https://x402.org/facilitator/supported (v2 `exact` on eip155:84532 and on solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1);
Adaptyv's payments docs (docs.adaptyvbio.com/api-reference/payments/pay-x402-exact: the 402 challenge comes base64 in the
PAYMENT-REQUIRED header, the answer goes in PAYMENT-SIGNATURE; production network eip155:8453 with Base USDC
0x833589fcd6edb6e08f4c7c32d4f71b54bda02913, extra name "USD Coin", version "2").

Nothing here sends money by itself: it builds and checks payloads. The lab's own server (or its facilitator) settles.
"""
from __future__ import annotations

import base64
import json
import secrets
import time

from . import evm

X402_VERSION = 2
BASE = "eip155:8453"
BASE_SEPOLIA = "eip155:84532"
SOLANA_DEVNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"
CHAIN_IDS = {BASE: 8453, BASE_SEPOLIA: 84532}
USDC = {BASE: "0x833589fCD6eDb6E08f4C7C32D4f71b54bdA02913", BASE_SEPOLIA: "0x036CbD53842c5426634e7929541eC2318f3dCF7e"}
TESTNETS = (BASE_SEPOLIA, SOLANA_DEVNET)       # what Knos pays on until mainnet is approved
HEADER_IN = "PAYMENT-REQUIRED"


class PayError(ValueError):
    pass


def _b64json(text: str) -> dict:
    pad = "=" * (-len(text) % 4)
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            got = json.loads(dec(text + pad))
            if isinstance(got, dict):
                return got
        except (ValueError, TypeError):
            continue
    raise PayError("the PAYMENT-REQUIRED header is not base64 JSON")


def decode_challenge(headers: dict, body: dict | None = None) -> dict:
    """The 402 challenge: {"x402Version", "resource", "accepts"}. v2 sends it in the PAYMENT-REQUIRED header; v1 in
    the body. Header names are compared without case."""
    low = {k.lower(): v for k, v in (headers or {}).items()}
    if HEADER_IN.lower() in low:
        got = _b64json(low[HEADER_IN.lower()])
    elif isinstance(body, dict) and isinstance(body.get("accepts"), list):
        got = body
    else:
        raise PayError("no x402 challenge: neither a PAYMENT-REQUIRED header nor `accepts` in the body")
    if not isinstance(got.get("accepts"), list) or not got["accepts"]:
        raise PayError("the challenge lists no payment requirement")
    return got


def choose(accepts: list[dict], networks=TESTNETS, scheme: str = "exact") -> dict:
    """The first requirement in a network Knos pays on (testnets only until mainnet is approved)."""
    for r in accepts:
        if r.get("scheme") == scheme and r.get("network") in networks:
            return r
    named = sorted({str(r.get("network")) for r in accepts})
    raise PayError(f"the lab asks for {', '.join(named)}; Knos pays only on {', '.join(networks)} until mainnet is approved")


def _amount(req: dict) -> int:
    v = req.get("amount", req.get("maxAmountRequired"))          # v2 `amount`, v1 `maxAmountRequired`
    if v is None or not str(v).isdigit():
        raise PayError("the requirement names no whole amount")
    return int(v)


def evm_payload(req: dict, priv: bytes, *, now: int | None = None, nonce: str | None = None, resource: dict | None = None) -> dict:
    """x402 v2 PaymentPayload for `exact` on EVM (EIP-3009), signed with `priv` (32 bytes). Never sent from here."""
    net = req.get("network")
    if net not in CHAIN_IDS:
        raise PayError(f"{net}: not an EVM network Knos knows (Base {BASE}, Base Sepolia {BASE_SEPOLIA})")
    extra = req.get("extra") or {}
    if extra.get("assetTransferMethod", "eip3009") != "eip3009":
        raise PayError("only the eip3009 transfer method is built (the Permit2 method is not)")
    if not extra.get("name") or not extra.get("version"):
        raise PayError("the requirement does not name the token's EIP-712 domain (extra.name, extra.version)")
    now = int(time.time()) if now is None else int(now)
    auth = {"from": evm.address(priv), "to": evm.checksum(req["payTo"]), "value": str(_amount(req)),
            "validAfter": str(now - 600), "validBefore": str(now + int(req.get("maxTimeoutSeconds", 60))),
            "nonce": nonce or "0x" + secrets.token_hex(32)}
    h = evm.transfer_with_authorization_hash(auth, name=extra["name"], version=extra["version"], chain_id=CHAIN_IDS[net],
                                             contract=req["asset"])
    sig = evm.sign_hash(priv, h)
    return {"x402Version": X402_VERSION, **({"resource": resource} if resource else {}), "accepted": req,
            "payload": {"signature": "0x" + sig.hex(), "authorization": auth}}


def check_evm(payload: dict, req: dict, now: int | None = None) -> list[str]:
    """Why this EVM payload does not pay this requirement ([] when the signature recovers to `from` and the payee,
    amount, asset, network and time window match). Balance and on-chain simulation are the facilitator's."""
    out = []
    try:
        auth, sig = payload["payload"]["authorization"], bytes.fromhex(payload["payload"]["signature"].removeprefix("0x"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return ["not an EVM exact payload"]
    acc = payload.get("accepted") or {}
    if acc.get("network") != req.get("network") or acc.get("asset", "").lower() != str(req.get("asset", "")).lower():
        out.append("another network or asset than the requirement's")
    if str(auth.get("to", "")).lower() != str(req.get("payTo", "")).lower():
        out.append("pays another address than the lab's payTo")
    if str(auth.get("value")) != str(_amount(req)):
        out.append("another amount than the requirement's")
    now = int(time.time()) if now is None else int(now)
    if not int(auth.get("validAfter", 0)) <= now < int(auth.get("validBefore", 0)):
        out.append("outside its validity window")
    extra = req.get("extra") or {}
    try:
        h = evm.transfer_with_authorization_hash(auth, name=extra.get("name", ""), version=extra.get("version", ""),
                                                 chain_id=CHAIN_IDS[req["network"]], contract=req["asset"])
        if len(sig) != 65 or evm.recover(h, sig).lower() != str(auth.get("from", "")).lower():
            out.append("the signature does not recover to `from`")
    except (KeyError, ValueError, TypeError):
        out.append("the signature cannot be checked")
    return out


def solana_payload(req: dict, payer, blockhash, *, decimals: int, resource: dict | None = None) -> dict:
    """x402 v2 `exact` on Solana devnet: a partially signed transfer the facilitator co-signs as fee payer."""
    if req.get("network") != SOLANA_DEVNET:
        raise PayError(f"{req.get('network')}: Knos pays Solana only on devnet")
    from ..money import x402_exact
    return x402_exact.payment(req, payer, blockhash, decimals=decimals, resource=resource)


def encode(payload: dict) -> str:
    """The PAYMENT-SIGNATURE header value: base64 of the payload's JSON."""
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def challenge_header(challenge: dict) -> str:
    """A PAYMENT-REQUIRED header value (for a lab stand-in or a test)."""
    return base64.b64encode(json.dumps(challenge, separators=(",", ":")).encode()).decode()
