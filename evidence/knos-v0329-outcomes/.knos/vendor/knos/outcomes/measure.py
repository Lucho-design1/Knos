"""One measurement: the spec, the lock written at funding, and the window's data in; a result JSON out.

    knos outcome measure outcome.yaml --lock outcome.lock.json [--repo .] [--out result.json] [--now UNIX]

The result says, for each tier, whether the one-sided lower confidence bound of the lift reached the tier's
min_lift, and gives the knos_pay audience a pay token for that tier's order must carry. The command exits 0 only when
nothing was refused and the bound reached success.min_lift; 1 otherwise (2 for a spec or data that cannot be read).

What makes a measurement refuse instead of pass or fail: the window has not closed; a cheat check found something
(knos.outcomes.tamper); fewer than MIN_GROUP items in either group.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import assign, data, metric, stats, tamper
from .spec import canonical, control_share, spec_hash, terms_hash, utc, validate

MIN_GROUP = 30
MODE = 0                 # knos_pay MERGE: the orders' mode byte; the terms say what is measured


def lock_for(spec: dict, rows_before: list[dict] | None = None, orders: list[dict] | None = None, code: str | None = None) -> dict:
    """The lock committed beside the spec before funding: everything the cheat checks compare, and the orders."""
    s = validate(spec)
    return {"v": 1, "spec_hash": spec_hash(s), "window": dict(s["window"]), "salt": s["control"]["salt"], "control_share": control_share(s),
            "measurement_commit": code or tamper.code_hash(),
            "data_hashes": {"history": data.history_hash(s, rows_before or [])}, "mode": MODE, "orders": orders or [], "payee": payees_text(s),
            "synthetic": bool(s["synthetic"])}


def payees_text(spec: dict) -> str:
    seller = spec["parties"]["seller"]
    return f"{seller['id']}.10000.{seller['address']}"


def audience(order: str, head: str, terms: bytes, mode: int, pr: int, payees: str) -> str:
    """knos3:pay:<order>:<head sha>:<terms hash hex>:<mode>:<pr>:<payees> (knos.settle.v2.pay.order_pay_audience)."""
    return f"knos3:pay:{order}:{head}:{terms.hex()}:{mode}:{pr}:{payees}"


def run(spec: dict, lock: dict, rows: list[dict], *, data_name: str, data_sha256: str, now: int, code: str | None = None) -> dict:
    s = validate(spec)
    h = spec_hash(s)
    window = data.in_window(s, rows)
    dup = data.duplicates(s, rows)
    share = control_share(s)
    idf, salt = s["data"]["id_field"], s["control"]["salt"]
    arms = {str(r[idf]): assign.arm(str(r[idf]), salt, share) for r in window}
    n = len(window)
    observed = (sum(1 for a in arms.values() if a == "control") / n) if n else None
    tol = assign.tolerance(share, n, s["control"].get("tolerance"))
    mismatches = 0
    if s["data"].get("arm_field"):
        af, tv = s["data"]["arm_field"], s["data"]["treated_value"]
        mismatches = sum(1 for r in window if (str(r.get(af)) == tv) != (arms[str(r[idf])] == "treated"))
    now_state = {"spec_hash": h, "window": dict(s["window"]), "salt": salt, "control_share": share,
                 "measurement_commit": code or tamper.code_hash(), "data_hashes": {"history": data.history_hash(s, rows)}}
    funded = {k: lock.get(k) for k in ("spec_hash", "window", "salt", "control_share", "measurement_commit", "data_hashes")}
    findings = tamper.merge(tamper.check(funded, now_state, observed_share=observed, tolerance=tol, duplicate_ids=dup, arm_mismatches=mismatches),
                            tamper.library(funded, now_state, tol))
    why: list[str] = []
    if now < utc(s["window"]["end"]):
        why.append(f"the window closes at {s['window']['end']}; a measurement before then is refused")
    if findings:
        why += [f"{f.category}: {f.detail}" for f in findings]
    tree = metric.compile_formula(s["metric"]["formula"])
    groups: dict[str, list[float]] = {"treated": [], "control": []}
    for r in window:
        groups[arms[str(r[idf])]].append(metric.value(tree, r))
    if min(len(groups["treated"]), len(groups["control"])) < MIN_GROUP:
        why.append(f"each group needs at least {MIN_GROUP} items in the window (treated {len(groups['treated'])}, control {len(groups['control'])})")
    numbers: dict = {}
    if min(len(groups["treated"]), len(groups["control"])) >= 1:
        try:
            numbers = stats.measure(groups["treated"], groups["control"], confidence=s["success"]["confidence"],
                                    resamples=s["bootstrap"]["resamples"], seed=s["bootstrap"]["seed"],
                                    kind=s["metric"]["lift"], direction=s["metric"]["direction"])
        except ValueError as e:
            why.append(str(e))
    refused = bool(why)
    lb = numbers.get("lower_bound")
    orders = {int(o["tier"]): o for o in lock.get("orders", [])}
    tiers = []
    for k, t in enumerate(s["tiers"]):
        ok = (not refused) and lb is not None and lb >= t["min_lift"]
        row = {"tier": k, "name": t["name"], "min_lift": t["min_lift"], "amount": t["amount"], "passed": ok}
        o = orders.get(k)
        if o:
            row["order"] = o["address"]
            if ok:
                row["audience"] = audience(o["address"], data_name, terms_hash(s, k), int(lock.get("mode", MODE)), int(s["escrow"]["issue"]), payees_text(s))
        tiers.append(row)
    passed = (not refused) and lb is not None and lb >= s["success"]["min_lift"]
    result = {"v": 1, "kind": "knos-outcome-result", "spec_hash": h, "title": s["title"], "synthetic": bool(s["synthetic"]),
              "metric": s["metric"]["name"], "window": dict(s["window"]), "data": {"name": data_name, "sha256": data_sha256, "rows": len(rows),
                                                                                   "in_window": n, "source": s["data"]["source"]},
              "control": {"share": share, "observed": observed, "tolerance": tol, "salt_sha256": hashlib.sha256(salt.encode()).hexdigest()},
              "code_hash": now_state["measurement_commit"], **numbers, "passed": passed, "refused": refused, "why": why,
              "findings": [f.to_dict() for f in findings], "tiers": tiers, "measured_at": now, "cluster": s["escrow"]["cluster"]}
    result["result_hash"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def summary(result: dict) -> str:
    lines = [f"{result['title']}{' (SYNTHETIC data)' if result['synthetic'] and 'SYNTHETIC' not in result['title'] else ''}",
             f"spec {result['spec_hash'][:16]}  data {result['data']['name'][:12]}  items in window {result['data']['in_window']}"]
    if "lift" in result:
        lines.append(f"treated {result['treated']['metric']:.4f} (n={result['treated']['n']})  control {result['control']['metric']:.4f} "
                     f"(n={result['control']['n']})  lift {result['lift']:+.4f}  lower bound at {result['confidence']:.0%}: {result['lower_bound']:+.4f}  "
                     f"(bootstrap {result['bootstrap']['resamples']}, seed {result['bootstrap']['seed']})")
    for t in result["tiers"]:
        lines.append(f"  tier {t['name']:<12} min lift {t['min_lift']:+.3f}  {'PASS' if t['passed'] else 'no'}")
    lines.append("REFUSED: " + "; ".join(result["why"]) if result["refused"] else ("PASSED" if result["passed"] else "NOT REACHED"))
    return "\n".join(lines)


def main_measure(spec_path: Path, lock_path: Path, repo: Path | None, out: Path | None, now: int | None, data_file: Path | None = None) -> int:
    import time
    from .spec import load
    s = load(spec_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if data_file is not None:
        raw = data_file.read_bytes()
        rows, name, digest = data.read(s, raw=raw)
    else:
        rows, name, digest = data.read(s, repo)
    result = run(s, lock, rows, data_name=name, data_sha256=digest, now=int(now if now is not None else time.time()))
    text = json.dumps(result, indent=2, sort_keys=True)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
    print(summary(result))
    return 0 if result["passed"] else 1
