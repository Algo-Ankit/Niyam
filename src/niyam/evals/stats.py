"""Paired bootstrap confidence intervals for comparing two systems on the same items."""

import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0


def paired_bootstrap(
    baseline: Sequence[float], candidate: Sequence[float], resamples: int = 2000, seed: int = 0
) -> Interval:
    """95% interval for mean(candidate - baseline), resampling items with replacement."""
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("need two equal, non-empty score lists")
    diffs = [c - b for b, c in zip(baseline, candidate, strict=True)]
    rng = random.Random(seed)  # noqa: S311  # resampling for statistics, not security
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return Interval(
        round(sum(diffs) / n, 3),
        round(means[int(0.025 * resamples)], 3),
        round(means[int(0.975 * resamples) - 1], 3),
    )
