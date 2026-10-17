"""Historial de latencia por dispositivo para la gráfica de la vista general (5 min, 1 h y 24 h)."""

import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..hub import hub
from ..models import LatencyMinute, User
from ..security import current_user

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# Ventana -> (duración en segundos, tamaño de cada grupo de puntos en segundos)
WINDOWS = {"5m": (300, 0), "1h": (3600, 60), "24h": (86400, 300)}
# Máximo de puntos por dispositivo en la ventana corta, para no saturar la gráfica
MAX_RAW_POINTS = 300


@router.get("/latency")
def latency(window: Literal["5m", "1h", "24h"] = "5m", db: Session = Depends(get_db),
            _: User = Depends(current_user)) -> dict:
    """Devuelve una serie de puntos [instante, latencia] por dispositivo."""
    span, bucket = WINDOWS[window]
    since = time.time() - span
    if bucket == 0:
        # Ventana corta: puntos individuales guardados en memoria;
        # si hay demasiados, se toma uno de cada varios
        out = {}
        for device_id, points in hub.latency_series().items():
            recent = [p for p in points if p[0] >= since]
            step = max(1, len(recent) // MAX_RAW_POINTS)
            out[device_id] = [[round(t, 3), v] for t, v in recent[::step]]
        return {"window": window, "series": out}

    # Ventanas largas: medias por minuto guardadas en la base de datos más el minuto en curso,
    # agrupadas en intervalos; cada media se pondera por su número de inferencias
    acc: dict[str, dict[int, list[float]]] = {}

    def add(device_id: str, ts: float, avg: float, count: int) -> None:
        key = int(ts // bucket) * bucket
        b = acc.setdefault(device_id, {}).setdefault(key, [0.0, 0])
        b[0] += avg * count
        b[1] += count

    rows = db.query(LatencyMinute).filter(
        LatencyMinute.minute >= datetime.fromtimestamp(since, UTC) - timedelta(minutes=1)
    )
    for r in rows:
        minute = r.minute if r.minute.tzinfo else r.minute.replace(tzinfo=UTC)
        add(r.device_id, minute.timestamp(), r.avg, r.count)
    for device_id, minute, avg, _peak, count in hub.open_buckets():
        if minute >= since:
            add(device_id, minute, avg, count)
    series = {
        d: [[float(k), round(s / c, 2)] for k, (s, c) in sorted(b.items()) if c and k >= since - bucket]
        for d, b in acc.items()
    }
    return {"window": window, "series": series}
