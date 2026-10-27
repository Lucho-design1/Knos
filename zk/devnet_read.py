"""The knos_zk devnet runs of 14 Oct 2026 read back from devnet into zk/fixtures/score64/devnet.json, in the shape
zk/devnet_demo.py writes (that demo sent them; this only reads, so the fixture holds what the chain says and no key
is needed). The order is the demo's: the fixture proof, a lower-bar claim, a flipped bit of C, then verify-and-record.

    python zk/devnet_read.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src")]
from knos import chain  # noqa: E402
from knos.zk import client, groth16  # noqa: E402

URL = "https://api.devnet.solana.com"
RUNS = {"verify": "4EzR4jrR2bdw88HPnmet5pEZz9Ki2NDEgMTUdpBpW2L8spaQMZYr87Vhjqijuvcmqpov3eHEwPLZz8NeauBuKH5N",
        "tampered_threshold": "jdnmV8ZBF8WAAT2pp9PuZqGBJurHR4HykLPE3fGLibNaxETVwrMe7S1pYomSdaxcbAf1dYx91Ux1BBKTA5QUPRL",
        "tampered_proof_c": "57HjoQzHiN5jfG1tibkW5tAcUeM1G526iFXDHXyAKrK78DktG3kSzm7RyYbhE5jrgcQnvgY79gQJV6ftM1QeHuM8",
        "verify_and_record": "5iYyt9DneRCyvLXTspDxFgEzSKRUBhJYDkRi2zc2QmRcfGZnhEGcNtnjWmToQdFE81xtXCzraBD1E4oquJAuD4CT"}
DEPLOY = "5Y7hVQqk7VTLrepWbK9CFkhVmcCX4vTAYKCLMSLY5idoXwwn9z9thKMskJdHAYyb2ipLNj5Jc57XZFkbhwQ6frcU"


def run(sig: str) -> dict:
    tx = chain.call(URL, "getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    meta = tx["meta"]
    logs = meta.get("logMessages") or []
    return {"signature": sig, "compute_units": meta.get("computeUnitsConsumed"), "err": meta.get("err"), "slot": tx["slot"],
            "program_log": [ln for ln in logs if "knos_zk" in ln or "consumed" in ln or "failed" in ln]}


def main() -> None:
    program = client.DEVNET_PROGRAM_ID
    _vk, _proof, inputs = groth16.load_dir(HERE / "fixtures" / "score64")
    verdict, _ = client.verdict_address(__import__("solders.pubkey", fromlist=["Pubkey"]).Pubkey.from_string(program), inputs)
    have = chain.call(URL, "getAccountInfo", [str(verdict), {"encoding": "base64", "commitment": "confirmed"}])["value"]
    ok, why = client.payable(have["owner"], base64.b64decode(have["data"][0]), __import__("solders.pubkey", fromlist=["Pubkey"]).Pubkey.from_string(program),
                             spec_hash=inputs[0], bar=48, pred_hash=inputs[1]) if have else (False, ["no verdict account"])
    doc = {"SYNTHETIC": "the hidden set is the made-up sample of zk/score_circuit; devnet only; TOY verifying key",
           "cluster": "devnet", "program_id": program, "deploy": DEPLOY, "verdict_account": str(verdict),
           "payable": ok, "payable_reasons": why, "read_back": "zk/devnet_read.py, from devnet",
           "runs": {k: run(s) for k, s in RUNS.items()}}
    out = HERE / "fixtures" / "score64" / "devnet.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: (v["err"], v["compute_units"]) for k, v in doc["runs"].items()}), doc["payable"])


if __name__ == "__main__":
    main()
