"""The outcome rules of the cheat library: what may not change between funding and measurement when Knos pays for a
measured result (TASK-OUTCOMES item 6). Each compares what was committed at funding with what the measurement saw.

    funded / now: {"spec_hash": hex, "window": {"start", "end"}, "salt": str, "control_share": float,
                   "measurement_commit": sha, "data_hashes": {path: sha256}}        (any key may be missing)

`data_hashes` at funding names the rows already in the window's data (files that existed before the window opened):
a file that changes after funding, or disappears, is data tampering. New files are new data and are not refused.
"""

from __future__ import annotations

from .library import Finding, Rule, add_rule

OUTCOME_RULES = (
    ("outcome_spec_hash_changed", "spec_hash_changed", "the signed outcome spec changed after funding"),
    ("outcome_window_changed", "window_changed", "the measurement window changed after funding"),
    ("outcome_salt_changed", "salt_changed", "the assignment salt changed after it was committed"),
    ("outcome_control_drift", "control_drift", "the control group's share drifted beyond tolerance"),
    ("outcome_measurement_code_drift", "measurement_code_drift", "the measurement code is not the pinned commit"),
    ("outcome_data_tampered", "data_tampering", "data that existed at funding was edited or removed"),
)
for _id, _cat, _title in OUTCOME_RULES:
    add_rule(Rule(_id, _cat, _title, kind="outcome"))


def scan_outcome(funded: dict, now: dict, *, control_tolerance: float = 0.02) -> list[Finding]:
    """Every outcome cheat between the funded commitment and what the measurement saw. A key the funded side does
    not have is not checked; a key the funded side has and the measurement lacks is a change."""
    funded, now = funded or {}, now or {}
    out: list[Finding] = []

    def add(rule: str, detail: str, path: str = "") -> None:
        from .library import RULES
        r = RULES[rule]
        out.append(Finding(rule, r.category, path, detail, r.severity))

    if funded.get("spec_hash") and now.get("spec_hash") != funded["spec_hash"]:
        add("outcome_spec_hash_changed", f"funded {str(funded['spec_hash'])[:16]}, measured {str(now.get('spec_hash'))[:16]}")
    if funded.get("window") is not None and (now.get("window") or {}) != funded["window"]:
        add("outcome_window_changed", f"funded {funded['window']}, measured {now.get('window')}")
    if funded.get("salt") is not None and now.get("salt") != funded["salt"]:
        add("outcome_salt_changed", "the salt differs from the one committed before the window")
    if funded.get("control_share") is not None:
        want, got = float(funded["control_share"]), now.get("control_share")
        if got is None or abs(float(got) - want) > control_tolerance:
            add("outcome_control_drift", f"agreed {want:.3f}, observed {got if got is None else round(float(got), 4)} "
                                         f"(tolerance {control_tolerance})")
    if funded.get("measurement_commit") and now.get("measurement_commit") != funded["measurement_commit"]:
        add("outcome_measurement_code_drift", f"pinned {funded['measurement_commit']}, ran {now.get('measurement_commit')}")
    was, seen = funded.get("data_hashes") or {}, now.get("data_hashes") or {}
    for path in sorted(was):
        if seen.get(path) != was[path]:
            add("outcome_data_tampered", "removed after funding" if path not in seen else "edited after funding", path)
    return out
