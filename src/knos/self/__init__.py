"""Knos builds Knos: safe recursive self-improvement on top of the referee and Knos Gate (targets.yml).

Agents change PRODUCT code only; the referee that judges them is MAIN's and out of their reach; every attempt, verdict,
cheat caught and payout goes to Knos Record; every accepted version stays in an archive whose lineage chooses where
agents build next.

    from knos.self import config, judge, loop, archive, referee_gate, payout, publog, tiers, rules
    config.load()                       targets.yml (founder-owned) + CODEOWNERS: the trusted core and the product
    loop.Loop(repo, state).run(...)     one iteration: referee from main -> cap -> canary -> devnet bounty -> record
    referee_gate.referee_change(...)    a referee change: red-team gate (>= current), shadow, founder signature
"""

from __future__ import annotations

__all__ = ["archive", "config", "judge", "loop", "payout", "publog", "referee_gate", "rules", "tiers"]
