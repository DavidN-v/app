"""Detección de drift con Population Stability Index (PSI)."""

import math
from collections.abc import Sequence

BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0000001]


def histogram(values: Sequence[float], bins: Sequence[float] = BINS) -> list[float]:
    counts = [0] * (len(bins) - 1)
    for v in values:
        for i in range(len(bins) - 1):
            if bins[i] <= v < bins[i + 1]:
                counts[i] += 1
                break
    total = sum(counts) or 1
    return [c / total for c in counts]


def psi(expected: Sequence[float], actual: Sequence[float], eps: float = 1e-4) -> float:
    """PSI entre dos distribuciones normalizadas. <0.1 estable, 0.1-0.2 moderado, >0.2 drift."""
    if len(expected) != len(actual):
        raise ValueError("Las distribuciones deben tener el mismo número de bins")
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return total
