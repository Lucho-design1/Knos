"""Lift and its confidence interval: a percentile bootstrap with a fixed, logged seed.

    resample  B times: draw n_t treated values with replacement from the treated values and n_c control values from
              the control values (each group on its own, as it was split), and compute the lift of the two means.
    bound     the one-sided lower bound at `confidence` is the (1 - confidence) quantile of the B lifts (the
              "lower" method of numpy.quantile: the k-th smallest, k = floor((1 - confidence) * (B - 1))).
    passes    a tier passes when that lower bound is at least its min_lift.

The random draws are Python's Mersenne Twister (random.Random(seed)) through `Random.choices`, whose algorithm and
output for a given seed have not changed since Python 3.6, so the same seed and data give the same interval on any
machine. A normal-approximation interval is reported beside it as a cross-check, never used to decide.
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist

from .metric import lift as lift_of


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def bootstrap_lifts(treated: list[float], control: list[float], resamples: int, seed: int, kind: str, direction: str) -> list[float]:
    """The B resampled lifts, sorted. Resamples whose control mean is 0 under a relative lift are dropped (they
    have no size); the count of those is len(result) short of B."""
    if not treated or not control:
        raise ValueError("both groups need at least one item")
    rng = random.Random(seed)
    nt, nc = len(treated), len(control)
    out: list[float] = []
    for _ in range(resamples):
        t = sum(rng.choices(treated, k=nt)) / nt
        c = sum(rng.choices(control, k=nc)) / nc
        try:
            out.append(lift_of(t, c, kind, direction))
        except ValueError:
            continue
    out.sort()
    return out


def lower_quantile(sorted_xs: list[float], q: float) -> float:
    """numpy.quantile(xs, q, method="lower") for sorted xs."""
    k = int(math.floor(q * (len(sorted_xs) - 1)))
    return sorted_xs[max(0, min(k, len(sorted_xs) - 1))]


def normal_interval(treated: list[float], control: list[float], confidence: float, kind: str, direction: str) -> tuple[float, float]:
    """(lower, upper) two-sided interval at `confidence` from the delta method; a cross-check only."""
    mt, mc = mean(treated), mean(control)
    vt = sum((x - mt) ** 2 for x in treated) / max(1, len(treated) - 1) / len(treated)
    vc = sum((x - mc) ** 2 for x in control) / max(1, len(control) - 1) / len(control)
    point = lift_of(mt, mc, kind, direction)
    if kind == "absolute":
        se = math.sqrt(vt + vc)
    else:
        # d/dt = ±1/c ; d/dc = ∓t/c^2
        se = math.sqrt(vt / mc ** 2 + (mt ** 2) * vc / mc ** 4)
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    return point - z * se, point + z * se


def measure(treated: list[float], control: list[float], *, confidence: float, resamples: int, seed: int, kind: str, direction: str) -> dict:
    """The numbers a result carries: the two means, the lift, the one-sided bootstrap lower bound at `confidence`,
    a two-sided bootstrap interval at the same level, and the normal cross-check."""
    lifts = bootstrap_lifts(treated, control, resamples, seed, kind, direction)
    if not lifts:
        raise ValueError("every resample had a control mean of 0")
    mt, mc = mean(treated), mean(control)
    lo_one = lower_quantile(lifts, 1 - confidence)
    lo_two, hi_two = lower_quantile(lifts, (1 - confidence) / 2), lower_quantile(lifts, 1 - (1 - confidence) / 2)
    n_lo, n_hi = normal_interval(treated, control, confidence, kind, direction)
    return {"treated": {"n": len(treated), "metric": mt}, "control": {"n": len(control), "metric": mc},
            "lift": lift_of(mt, mc, kind, direction), "lift_kind": kind, "direction": direction, "confidence": confidence,
            "lower_bound": lo_one, "interval": [lo_two, hi_two], "normal_interval": [n_lo, n_hi],
            "bootstrap": {"method": "percentile, groups resampled separately, numpy 'lower' quantile", "resamples": resamples,
                          "used": len(lifts), "seed": seed, "rng": "random.Random (MT19937) .choices"}}


def tiers_passed(lower_bound: float, tiers: list[dict]) -> list[bool]:
    return [lower_bound >= t["min_lift"] for t in tiers]
