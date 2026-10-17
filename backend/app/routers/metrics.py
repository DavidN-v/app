"""Historial de latencia por dispositivo para la gráfica (5 min, 1 h, 24 h)."""

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

# ventana -> (segundos, tamaño del bucket en segundos)
WINDOWS = {"5m": (300, 0), "1h": (3600, 60), "24h": (86400, 300)}
MAX_RAW_POINTS = 300


@router.get("/latency")
def latency(window: Literal["5m", "1h", "24h"] = "5m", db: Session = Depends(get_db),
            _: User = Depends(current_user)) -> dict:
    span, bucket = WINDOWS[window]
    since = time.time() - span
    if bucket == 0:
        # Ventana corta: puntos crudos del buffer en memoria, aligerados si hay demasiados
        out = {}
        for device_id, points in hub.latency_series().items():
            recent = [p for p in points if p[0] >= since]
            step = max(1, len(recent) // MAX_RAW_POINTS)
            out[device_id] = [[round(t, 3), v] for t, v in recent[::step]]
        return {"window": window, "series": out}

    # Ventanas largas: minutos guardados + el minuto en curso, agrupados por bucket
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
