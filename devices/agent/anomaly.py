"""Detector de anomalías en la telemetría de la flota.

Para cada dispositivo y cada métrica (CPU, RAM, temperatura) se guardan las últimas lecturas.
Una lectura nueva se considera anómala si se aleja mucho de lo habitual, medido con la
puntuación z: z = (valor - media) / desviación típica. Es decir, cuántas desviaciones típicas
se separa el valor de la media reciente. Con el umbral por defecto (4) se marcan solo los
cambios muy bruscos, lo que evita falsas alarmas por el ruido normal de las medidas.
"""

import math
from collections import defaultdict, deque
from dataclasses import dataclass

METRICS = ("cpu", "ram", "temp")


@dataclass
class Verdict:
    """Resultado de analizar una lectura."""

    device: str
    anomalous: bool
    worst_metric: str | None
    z: float
    #: 1.0 = lectura perfectamente normal, tiende a 0 cuanto más se aleja de lo habitual
    normality: float


class RollingStats:
    """Últimos valores de una métrica y cálculo de su puntuación z."""

    def __init__(self, window: int) -> None:
        self.values: deque[float] = deque(maxlen=window)

    def push(self, value: float) -> None:
        self.values.append(value)

    def zscore(self, value: float) -> float | None:
        n = len(self.values)
        if n < 10:  # sin historia suficiente no se juzga
            return None
        mean = sum(self.values) / n
        var = sum((v - mean) ** 2 for v in self.values) / (n - 1)
        std = max(math.sqrt(var), 0.5)  # suelo: evita alarmas por ruido en señales muy planas
        return (value - mean) / std


class AnomalyDetector:
    """Mantiene una historia separada para cada pareja (dispositivo, métrica)."""

    def __init__(self, window: int = 60, threshold: float = 4.0) -> None:
        self.threshold = threshold
        self.stats: dict[tuple[str, str], RollingStats] = defaultdict(lambda: RollingStats(window))

    def observe(self, device: str, reading: dict) -> Verdict:
        """Juzga la lectura contra la historia del dispositivo y después la incorpora."""
        worst, worst_z = None, 0.0
        for metric in METRICS:
            value = reading.get(metric)
            if value is None:
                continue
            stats = self.stats[(device, metric)]
            z = stats.zscore(float(value))
            if z is not None and abs(z) > abs(worst_z):
                worst, worst_z = metric, z
            stats.push(float(value))
        anomalous = abs(worst_z) >= self.threshold
        normality = math.exp(-((worst_z / self.threshold) ** 2))
        return Verdict(device, anomalous, worst if anomalous else None, round(worst_z, 2), round(normality, 3))
