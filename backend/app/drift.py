"""Detección de drift (deriva) de un modelo.

Se dice que un modelo sufre drift cuando los datos que recibe en producción dejan de parecerse
a los datos con los que se validó, y por tanto sus resultados dejan de ser fiables. Aquí se
detecta comparando la distribución de las confianzas que da el modelo en el dispositivo con
la distribución de referencia medida durante la validación.

La comparación se hace con el índice de estabilidad poblacional (PSI):
    PSI = suma sobre cada intervalo de (actual - referencia) * ln(actual / referencia)
Por convención, menos de 0,1 indica estabilidad, entre 0,1 y 0,2 un cambio moderado y más de
0,2 un cambio significativo.
"""

import math
from collections.abc import Sequence

# Diez intervalos de confianza de igual anchura entre 0 y 1. El último límite es un poco mayor
# que 1 para que una confianza exactamente igual a 1 entre en el último intervalo.
BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0000001]


def histogram(values: Sequence[float], bins: Sequence[float] = BINS) -> list[float]:
    """Proporción de valores que cae en cada intervalo; la suma total es 1."""
    counts = [0] * (len(bins) - 1)
    for v in values:
        for i in range(len(bins) - 1):
            if bins[i] <= v < bins[i + 1]:
                counts[i] += 1
                break
    total = sum(counts) or 1
    return [c / total for c in counts]


def psi(expected: Sequence[float], actual: Sequence[float], eps: float = 1e-4) -> float:
    """Calcula el PSI entre la distribución de referencia y la observada."""
    if len(expected) != len(actual):
        raise ValueError("Las distribuciones deben tener el mismo número de bins")
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        # Un intervalo vacío daría un logaritmo de cero; se sustituye por un valor muy pequeño
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return total
