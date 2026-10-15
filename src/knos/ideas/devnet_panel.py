"""Wall 1 end to end on devnet for ANY idea and every kind of stage: lock, sign, release or refund, through the same
code as `knos idea commit | sign | release | refund`.

    python -m knos.ideas.devnet_panel --wallets DIR --referees DIR2 --claim FILE [--idea KEY] --payee SPEC \\
        --program ID --mint MINT [--stages oracle:bps,...] [--review stage2=pass,stage3=fail] [--unlisted-panel] --out FILE.json

  --claim    a Claim record (knos idea get --out), a commitment file, or knos.ideas.devnet's output with --idea A|B|C
  --wallets  the buyer's folder: payer.json funds the stages and relays the verdicts
  --referees the referees' folder: referee-1..3.json. Refused when it is the buyer's folder or inside it: a buyer never
             holds the keys that judge its own money. (In this demo one machine plays all three referees, so they are
             NOT independent; a real panel is three parties, each running `knos idea sign` where its key is.)
  --review   referee_pass / lab_qc stages: each referee's result on a review report this demo writes (SYNTHETIC)

Each stage: every referee signs what it reads (automatic oracles live from the public source; review stages from the
report); M PASS verdicts release it to the committed payee, M FAIL verdicts refund it to the buyer, a pending oracle
signs nothing and the stage stays locked. Every result is read back from the chain: a refund is never called a release.
Test units of the demo's own mint: test money, 0 revenue. Devnet only. Never prints a key.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from .. import chain
from ..settle.v2 import pay
from . import IdeaError, check as check_record
from . import commit as C
from .cli import _stages
from .devnet import _key, _x

UNIT = 1_000_000


def _claim(path: Path, idea: str | None) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("kind") == C.KIND:
        return check_record(doc["claim"])
    if "ideas" in doc:
        if not idea:
            raise IdeaError("this file holds several ideas: name one with --idea")
        return check_record(doc["ideas"][idea]["claim"])
    return check_record(doc)


def _inside(child: Path, parent: Path) -> bool:
    c, p = child.expanduser().resolve(), parent.expanduser().resolve()
    return c == p or p in c.parents


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos.ideas.devnet_panel")
    ap.add_argument("--wallets", required=True, type=Path)
    ap.add_argument("--referees", required=True, type=Path)
    ap.add_argument("--claim", required=True, type=Path)
    ap.add_argument("--idea")
    ap.add_argument("--payee", required=True)
    ap.add_argument("--program", required=True)
    ap.add_argument("--mint", required=True)
    ap.add_argument("--stages")
    ap.add_argument("--units", type=int, default=10)
    ap.add_argument("--price", type=int, default=4)
    ap.add_argument("--review", default="", help="stageN=pass|fail for referee_pass / lab_qc stages")
    ap.add_argument("--unlisted-panel", action="store_true")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if _inside(a.referees, a.wallets) or _inside(a.wallets, a.referees):
        print("refused: the referees' keys may not live in (or around) the buyer's folder", file=sys.stderr)
        return 2
    led = chain.ledger()
    if "devnet" not in led.url:
        print("devnet only", file=sys.stderr)
        return 2
    claim = _claim(a.claim, a.idea)
    program, mint = Pubkey.from_string(a.program), Pubkey.from_string(a.mint)
    payer = _key(a.wallets / "payer.json")
    a.referees.mkdir(parents=True, exist_ok=True)
    referees = [_key(a.referees / f"referee-{k}.json") for k in (1, 2, 3)]
    payee = C.parse_payee(a.payee)
    reviews = dict(x.split("=", 1) for x in a.review.split(",") if "=" in x)
    rows: list[dict] = []

    def note(step: str, sig: str | None) -> None:
        rows.append({"step": step, "signature": sig, "explorer": _x(sig) if sig else None})
        print(step, sig or "", flush=True)

    tok = pay.ata(payer.pubkey(), mint)
    have = int(chain.call(led.url, "getTokenAccountBalance", [str(tok)])["value"]["amount"]) if led.account(tok) else 0
    need = a.units * a.price * UNIT * 2
    if have < need:      # the demo's own test mint: the payer is its mint authority
        ix = Instruction(pay.TOKEN, bytes([7]) + (need - have).to_bytes(8, "little"),
                         [AccountMeta(mint, False, True), AccountMeta(tok, False, True), AccountMeta(payer.pubkey(), True, False)])
        note(f"mint {(need - have) / UNIT:g} test units to the buyer (the demo's own test mint)", led.send([ix], payer))
    commit_file = a.out.with_suffix(".commit.json")
    if commit_file.exists():
        doc = C.load(commit_file)
    else:
        doc = C.commit(claim, units=a.units, price=a.price, payee=payee, funder=payer, funder_token=tok, mint=mint, led=led,
                       stages=_stages(a.stages), panel=(2, [str(r.pubkey()) for r in referees]), program=program,
                       unlisted_panel=a.unlisted_panel)
        commit_file.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        for stage, r in doc["orders"].items():
            note(f"lock {stage} ({r['oracle']}, {r['amount'] / UNIT:g} test units) as a PANEL order, 2 of 3 referees "
                 f"{doc['panel']['label'] or ''}".rstrip(), r["signature"])
    results = {}
    for stage, r in doc["orders"].items():
        if led.account(Pubkey.from_string(r["order"])) is None:
            results[stage] = C.outcome(doc, stage, led)
            continue
        recs, why = [], None
        for ref in referees:
            kw = {}
            if r["oracle"] in ("referee_pass", "lab_qc"):
                word = reviews.get(stage)
                if word not in ("pass", "fail"):
                    why = "no review result given for this stage (pending)"
                    break
                report = a.out.with_name(f"{a.out.stem}-{stage}-review.txt")
                report.write_text(f"SYNTHETIC review report for {claim['id']} {stage} ({r['oracle']}): {word.upper()}\n", encoding="utf-8")
                kw = {"passed": word == "pass", "review": report}
            try:
                recs.append(C.sign(doc, stage, ref, led, **kw))
            except IdeaError as e:
                why = str(e)
                break
        if not recs:
            results[stage] = {"stage": stage, "oracle": r["oracle"], "status": f"locked: pending ({why})", "sent": []}
            note(f"{stage} ({r['oracle']}): nothing signed: {why}", None)
            continue
        verdict = recs[0]["verdict"]
        got = (C.release if verdict == "PASS" else C.refund)(doc, stage, recs[:2], payer, led)
        results[stage] = got
        for n, s in enumerate(got["sent"], 1):
            note(f"{stage} ({r['oracle']}) verdict {verdict}: referee {s['referee'][:8]} signs, {n} of 2"
                 + (f" -> {got['status'].upper()}" if n == len(got["sent"]) else " (recorded)"), s["signature"])
    acct = led.account(pay.ata(Pubkey.from_string(payee["wallet"]), mint))
    released = [s for s, g in results.items() if g["status"] == "released"]
    refunded = [s for s, g in results.items() if g["status"] == "refunded"]
    out = {"what": f"knos idea on devnet: {claim['field']} claim {claim['id']}; stages released by 2-of-3 referee verdicts: "
                   f"{', '.join(released) or 'none'}; refunded: {', '.join(refunded) or 'none'} (read from the chain); "
                   "test units of the demo's own mint, 0 revenue",
           "claim": claim["id"], "field": claim["field"], "statement": claim["statement"], "program": str(program), "mint": str(mint),
           "payee": payee, "panel": doc["panel"], "referees_note": "one machine plays all three referees in this demo: not independent",
           "commitment_file": str(commit_file), "results": results, "payee_units": (int.from_bytes(acct[64:72], "little") / UNIT) if acct else 0,
           "signatures": rows}
    a.out.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
