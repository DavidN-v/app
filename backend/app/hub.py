"""Estado en tiempo real guardado en memoria y envío de eventos a la consola.

Aquí se guardan los datos recientes que no merece la pena escribir en la base de datos en cada
mensaje: las últimas latencias, las confianzas para calcular el drift y las medias por minuto.
También se mantiene la lista de navegadores conectados por WebSocket para enviarles cada evento.

Los mensajes MQTT se procesan en un hilo distinto del de FastAPI. Por eso el acceso a los datos
se protege con un cerrojo (lock) y los eventos se entregan al bucle principal con
call_soon_threadsafe, que es la forma segura de pasar trabajo entre hilos en asyncio.
"""

import asyncio
import threading
import time
from collections import defaultdict, deque
from typing import Any

SERIES_LEN = 1200  # puntos por dispositivo (10 min a 2 Hz)
CONFIDENCE_LEN = 500


class LiveHub:
    """Almacén en memoria compartido por toda la API (hay una única instancia, `hub`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self.latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=SERIES_LEN))
        self.confidence: dict[str, deque] = defaultdict(lambda: deque(maxlen=CONFIDENCE_LEN))
        self.mqtt_rx: dict[str, int] = defaultdict(int)
        # (device_id, minuto epoch) -> [suma, cuenta, máximo]
        self._buckets: dict[tuple[str, int], list[float]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Guarda el bucle de eventos de FastAPI para poder enviarle eventos desde otros hilos."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Registra un navegador conectado; recibirá los eventos a través de esta cola."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def record_latency(self, device_id: str, value: float, ts: float | None = None) -> None:
        """Guarda la latencia en la serie reciente y la acumula en el minuto correspondiente."""
        ts = ts or time.time()
        with self._lock:
            self.latency[device_id].append((ts, value))
            b = self._buckets.setdefault((device_id, int(ts // 60) * 60), [0.0, 0, value])
            b[0] += value
            b[1] += 1
            b[2] = max(b[2], value)

    def recent_latency(self, device_id: str, n: int = 10) -> float | None:
        """Media de las últimas `n` inferencias: una muestra aislada no es una tendencia."""
        with self._lock:
            values = [v for _, v in list(self.latency.get(device_id, ()))[-n:]]
        return sum(values) / len(values) if values else None

    def drain_buckets(self, before: float) -> list[tuple[str, int, float, float, int]]:
        """Entrega los minutos ya cerrados (anteriores a `before`) para guardarlos."""
        with self._lock:
            done = [k for k in self._buckets if k[1] + 60 <= before]
            out = []
            for key in done:
                total, count, peak = self._buckets.pop(key)
                out.append((key[0], key[1], total / count, peak, int(count)))
            return out

    def open_buckets(self) -> list[tuple[str, int, float, float, int]]:
        """Minutos todavía en curso, para que las gráficas muestren también el minuto actual."""
        with self._lock:
            return [(k[0], k[1], v[0] / v[1], v[2], int(v[1])) for k, v in self._buckets.items() if v[1]]

    def record_confidence(self, device_id: str, value: float, model: str | None = None) -> None:
        # Se separa por modelo: tras un despliegue no se mezclan confianzas de modelos distintos
        with self._lock:
            self.confidence[f"{device_id}|{model or ''}"].append(value)

    def latency_series(self) -> dict[str, list[tuple[float, float]]]:
        with self._lock:
            return {k: list(v) for k, v in self.latency.items()}

    def confidences(self, device_id: str, model: str | None = None) -> list[float]:
        with self._lock:
            return list(self.confidence.get(f"{device_id}|{model or ''}", ()))

    def broadcast(self, event: dict[str, Any]) -> None:
        """Envía un evento a todos los navegadores conectados. Se puede llamar desde cualquier hilo."""
        if self._loop is None:
            return
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            self._loop.call_soon_threadsafe(_offer, q, event)


def _offer(q: asyncio.Queue, event: dict) -> None:
    # Un cliente lento no debe frenar a los demás: si su cola está llena, se descarta el evento.
    if not q.full():
        q.put_nowait(event)


hub = LiveHub()
