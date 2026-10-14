"""The Knos referee: Works, Wanted, Makeable. A verdict passes only when all three do.

    from knos import referee
    s = referee.seal(hidden_bundle, issue="1")             # before work starts: spec hash + locked judge hash
    w = referee.works(base, pr, s, hidden_dir=hidden_bundle)  # sealed tests, locked judge, cheat rules, re-run
    d = referee.wanted(orders, min_buyers=3, min_locked=300_000_000)
    m = referee.makeable(quotes, locked_price=300.0, min_margin=0.2)
    v = referee.verdict(w, d, m, spec_hash=s["spec_hash"])  # all three; written to Knos Record

docs/reference/REFEREE.md says what each check does and what it does not.
"""

from __future__ import annotations

from .check import Check
from .makeable import KINDS, Quote, makeable
from .maintainer import MODES, maintainer
from .seal import JUDGING_CODE, judge_hash, seal, seal_hash
from .verdict import judge_candidate, redact_hidden, reward, verdict
from .wanted import DemandBook, wanted
from .works import rerun_agrees, within_tolerance, works

__all__ = ["Check", "DemandBook", "JUDGING_CODE", "KINDS", "MODES", "Quote", "judge_candidate", "judge_hash", "maintainer",
           "makeable", "redact_hidden", "rerun_agrees", "reward", "seal", "seal_hash", "verdict", "wanted", "within_tolerance", "works"]
