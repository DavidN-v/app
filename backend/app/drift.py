"""Detección de drift (deriva) de un modelo."""

import math
from collections.abc import Sequence

# El último límite pasa de 1 para que una confianza de 1 entre en el último intervalo
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
    if len(expected) != len(actual):
        raise ValueError("Las distribuciones deben tener el mismo número de bins")
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        # Un intervalo vacío daría un logaritmo de cero; se sustituye por un valor muy pequeño
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return total
