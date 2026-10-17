"""Estado en vivo en memoria y difusión de eventos a los clientes WebSocket.

El ingestor MQTT corre en un hilo de paho, por eso `broadcast` es thread-safe:
reenvía los eventos al event loop de FastAPI con call_soon_threadsafe."""

import asyncio
import threading
import time
from collections import defaultdict, deque
from typing import Any

SERIES_LEN = 300  # puntos por dispositivo (~5 min a 1 Hz)
CONFIDENCE_LEN = 500


class LiveHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self.latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=SERIES_LEN))
        self.confidence: dict[str, deque] = defaultdict(lambda: deque(maxlen=CONFIDENCE_LEN))
        self.mqtt_rx: dict[str, int] = defaultdict(int)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def record_latency(self, device_id: str, value: float, ts: float | None = None) -> None:
        with self._lock:
            self.latency[device_id].append((ts or time.time(), value))

    def record_confidence(self, device_id: str, value: float) -> None:
        with self._lock:
            self.confidence[device_id].append(value)

    def latency_series(self) -> dict[str, list[tuple[float, float]]]:
        with self._lock:
            return {k: list(v) for k, v in self.latency.items()}

    def confidences(self, device_id: str) -> list[float]:
        with self._lock:
            return list(self.confidence.get(device_id, ()))

    def broadcast(self, event: dict[str, Any]) -> None:
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
