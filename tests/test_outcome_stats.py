"""Known-answer tests: the hash split, the metric's formula, the lift, and the bootstrap interval."""
from __future__ import annotations

import hashlib
import math

import pytest

from knos.outcomes import assign, metric, stats

ZERO_SALT = "00" * 16


def test_the_split_is_the_documented_hash_and_its_known_answers():
    for item in ("a", "SYN-1", "ticket-42"):
        d = hashlib.sha256(b"knos-outcome:v1:" + ZERO_SALT.encode() + b":" + item.encode()).digest()
        assert assign.position(item, ZERO_SALT) == int.from_bytes(d[:8], "big") / 2 ** 64
    assert assign.position("a", ZERO_SALT) == 0.6642652764527802
    assert assign.position("SYN-1", ZERO_SALT) == 0.6498714173947061
    assert assign.arm("a", ZERO_SALT, 0.2) == "treated" and assign.arm("a", ZERO_SALT, 0.7) == "control"


def test_the_split_is_deterministic_and_near_its_share_and_another_salt_moves_it():
    ids = [f"t{i}" for i in range(20_000)]
    one, two = assign.split(ids, ZERO_SALT, 0.2), assign.split(ids, ZERO_SALT, 0.2)
    assert one == two
    share = sum(a == "control" for a in one.values()) / len(ids)
    assert abs(share - 0.2) < assign.tolerance(0.2, len(ids))
    other = assign.split(ids, "11" * 16, 0.2)
    assert sum(one[i] != other[i] for i in ids) > 1000


def test_the_drift_tolerance():
    assert assign.tolerance(0.2, 100) == pytest.approx(4 * math.sqrt(0.16 / 100))
    assert assign.tolerance(0.2, 1_000_000) == pytest.approx(4 * math.sqrt(0.16 / 1_000_000))      # no floor (finding 21)
    assert assign.tolerance(0.2, 100, given=0.05) == 0.05


@pytest.mark.parametrize("formula,row,want", [
    ("1 if status == 'solved' and escalated == 0 else 0", {"status": "solved", "escalated": 0}, 1.0),
    ("1 if status == 'solved' and escalated == 0 else 0", {"status": "solved", "escalated": 1}, 0.0),
    ("minutes / 60", {"minutes": 90}, 1.5),
    ("max(a, b) - abs(c)", {"a": 2, "b": 5, "c": -1}, 4.0),
    ("channel in ('chat', 'web')", {"channel": "web"}, 1.0),
    ("0 < x <= 3", {"x": 4}, 0.0),
])
def test_formulas(formula, row, want):
    assert metric.value(formula, row) == want


@pytest.mark.parametrize("formula", ["__import__('os').system('x')", "x.__class__", "x[0]", "[y for y in x]", "lambda: 1", "open('f')", "eval('1')"])
def test_a_formula_evaluates_nothing_but_arithmetic_on_the_row(formula):
    with pytest.raises(metric.FormulaError):
        metric.value(formula, {"x": [1], "y": 1})


def test_a_missing_field_is_named():
    with pytest.raises(metric.FormulaError, match="status"):
        metric.value("status == 'x'", {})


def test_csv_text_reads_as_numbers_and_booleans():
    assert metric.row_values({"a": "3", "b": "2.5", "c": "true", "d": "", "e": "x"}) == {"a": 3, "b": 2.5, "c": True, "d": None, "e": "x"}


def test_lift_known_answers():
    assert metric.lift(0.6, 0.5, "relative", "higher") == pytest.approx(0.2)
    assert metric.lift(0.6, 0.5, "absolute", "higher") == pytest.approx(0.1)
    assert metric.lift(40, 50, "relative", "lower") == pytest.approx(0.2)        # 20% less time
    assert metric.lift(40, 50, "absolute", "lower") == pytest.approx(10)
    with pytest.raises(ValueError):
        metric.lift(0.5, 0.0, "relative", "higher")


T = [1, 1, 0, 1, 0, 1, 1, 0, 1, 1] * 5          # 0.7
C = [0, 1, 0, 0, 1, 0, 1, 0, 0, 0] * 5          # 0.3


def test_the_bootstrap_known_answers_for_a_fixed_seed():
    m = stats.measure(T, C, confidence=0.9, resamples=500, seed=42, kind="relative", direction="higher")
    assert m["lift"] == pytest.approx(4 / 3)
    assert m["lower_bound"] == 0.7894736842105264
    assert m["interval"] == [0.6842105263157895, 2.5]
    assert m["normal_interval"] == pytest.approx([0.4221403820993559, 2.2445262845673106])
    assert m["bootstrap"]["seed"] == 42 and m["bootstrap"]["resamples"] == 500 and m["bootstrap"]["used"] == 500
    a = stats.measure(T, C, confidence=0.9, resamples=500, seed=42, kind="absolute", direction="higher")
    assert a["lift"] == pytest.approx(0.4) and a["lower_bound"] == pytest.approx(0.28)


def test_the_same_seed_gives_the_same_interval_and_another_seed_another():
    one = stats.measure(T, C, confidence=0.95, resamples=300, seed=7, kind="absolute", direction="higher")
    assert one == stats.measure(T, C, confidence=0.95, resamples=300, seed=7, kind="absolute", direction="higher")
    assert one["lower_bound"] != stats.measure(T, C, confidence=0.95, resamples=300, seed=8, kind="absolute", direction="higher")["lower_bound"]


def test_identical_groups_have_no_lift_and_the_bound_is_below_zero():
    m = stats.measure(C, C, confidence=0.95, resamples=400, seed=1, kind="absolute", direction="higher")
    assert m["lift"] == 0 and m["lower_bound"] < 0 < m["interval"][1]


def test_the_bootstrap_bound_agrees_with_the_normal_approximation_on_a_large_sample():
    t = [1] * 560 + [0] * 440
    c = [1] * 500 + [0] * 500
    m = stats.measure(t, c, confidence=0.95, resamples=2000, seed=3, kind="absolute", direction="higher")
    se = math.sqrt(0.56 * 0.44 / 1000 + 0.25 / 1000)
    assert m["lower_bound"] == pytest.approx(0.06 - 1.645 * se, abs=0.008)


def test_the_lower_quantile_is_numpys_lower_method():
    xs = list(range(11))
    assert stats.lower_quantile(xs, 0.05) == 0 and stats.lower_quantile(xs, 0.5) == 5 and stats.lower_quantile(xs, 0.99) == 9
    np = pytest.importorskip("numpy")
    ys = sorted([0.3, 0.1, 0.7, 0.2, 0.9, 0.4, 0.8])
    for q in (0.05, 0.1, 0.25, 0.5, 0.9):
        assert stats.lower_quantile(ys, q) == float(np.quantile(ys, q, method="lower"))


def test_tiers_pass_on_the_lower_bound():
    assert stats.tiers_passed(0.12, [{"min_lift": 0.05}, {"min_lift": 0.10}, {"min_lift": 0.20}]) == [True, True, False]


def test_a_resample_with_a_zero_control_mean_is_refused_not_dropped():
    """Dropping those resamples would bias the bound toward the seller; the measurement refuses instead."""
    with pytest.raises(ValueError, match="control mean of 0"):
        stats.measure(T, [0] * 49 + [1], confidence=0.95, resamples=300, seed=1, kind="relative", direction="higher")
