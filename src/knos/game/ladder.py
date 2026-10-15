"""The public score of a game: what a player may learn from the referee about the sealed set, and no more.

Every attempt is judged on the referee's sealed `dev` set, which no player ever sees. Showing its exact score after
every attempt would let a player (or an agent in a loop) fit that set by trial and error: adaptive overfitting of a
holdout through a leaderboard. Knos shows the score through the Ladder mechanism of Blum and Hardt ("The Ladder: A
Reliable Leaderboard for Machine Learning Competitions", ICML 2015, arXiv 1502.04585): a player's shown score moves
only when an attempt beats that player's own shown best by more than `eta`, and then it moves to the new score
rounded to a multiple of `eta`. Smaller gains, and the noise a player would probe, are never shown.

This is the fixed-`eta` form of the mechanism (the paper also gives a parameter-free variant; Knos uses the fixed one
and says so). It protects the public board; it is not what pays. Payment follows the referee's verdict on a SECOND
sealed set (`final`), used once, at the end of the game, for each player's chosen attempt.
"""
from __future__ import annotations

import math

DEFAULT_ETA = 0.01


def rounded(score: float, eta: float, maximize: bool = True) -> float:
    """`score` rounded to a multiple of `eta`, toward the worse side (down for a score to maximize): a shown score is
    never better than the true one."""
    if eta <= 0:
        raise ValueError("eta: above 0")
    steps = score / eta
    k = math.floor(steps + 1e-9) if maximize else math.ceil(steps - 1e-9)
    return round(k * eta, 10)


def step(shown: float | None, score: float, eta: float = DEFAULT_ETA, maximize: bool = True) -> tuple[float | None, bool]:
    """One Ladder step for one player: (the shown score after this attempt, whether it moved). `shown` None: the
    player has no shown score yet, so any first score is shown (rounded)."""
    new = rounded(score, eta, maximize)
    if shown is None:
        return new, True
    better = score > shown + eta if maximize else score < shown - eta
    if better and new != shown:
        return new, True
    return shown, False
