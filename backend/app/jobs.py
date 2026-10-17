"""Tareas periódicas: watchdog de heartbeats y detección de drift."""

import asyncio
import contextlib
import logging
from datetime import UTC, timedelta

from sqlalchemy.orm import Session

from . import drift, policies, prom
from .alerting import raise_alert
from .config import get_settings
from .db import SessionLocal
from .hub import hub
from .models import Device, utcnow

log = logging.getLogger(__name__)
MIN_DRIFT_SAMPLES = 50


def check_heartbeats(db: Session) -> list[str]:
    cutoff = utcnow() - timedelta(seconds=get_settings().offline_after_s)
    stale = []
    for device in db.query(Device).filter_by(status="online"):
        last = device.last_seen
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is None or last < cutoff:
            device.status = "offline"
            prom.DEVICE_UP.labels(device.id).set(0)
            hub.broadcast({"type": "device_status", "data": {"id": device.id, "status": "offline"}})
            raise_alert(db, device.id, "offline", "warning",
                        f"{device.name} sin heartbeat desde hace más de "
                        f"{get_settings().offline_after_s}s")
            stale.append(device.id)
    db.commit()
    return stale


def check_drift(db: Session) -> dict[str, float]:
    threshold = policies.load(db).number("max_drift_psi", 0.2)
    results = {}
    for device in db.query(Device).filter(Device.current_model_id.isnot(None)):
        model = device.current_model
        reference = (model.metrics or {}).get("reference_confidence_hist")
        samples = hub.confidences(device.id)
        if not reference or len(samples) < MIN_DRIFT_SAMPLES:
            continue
        value = drift.psi(reference, drift.histogram(samples))
        results[device.id] = value
        prom.DRIFT_PSI.labels(device.id, f"{model.name}:{model.version}").set(value)
        if value > threshold:
            raise_alert(db, device.id, "drift", "warning",
                        f"Drift en {model.name} v{model.version} sobre {device.name}: "
                        f"PSI={value:.3f} (> {threshold:g})")
    db.commit()
    return results


async def run_forever(stop: asyncio.Event) -> None:
    settings = get_settings()
    ticks = 0
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(check_heartbeats, db)
                if ticks % max(1, settings.drift_interval_s // 5) == 0:
                    await asyncio.to_thread(check_drift, db)
        except Exception:
            log.exception("Error en tareas periódicas")
        ticks += 1
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5)
