"""Tareas periódicas: watchdog de heartbeats y detección de drift."""

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from . import audit, drift, policies, prom
from .alerting import raise_alert, resolve_alerts
from .config import get_settings
from .db import SessionLocal
from .hub import hub
from .models import Deployment, Device, LatencyMinute, utcnow

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
        samples = hub.confidences(device.id, model.name)
        if not reference or len(samples) < MIN_DRIFT_SAMPLES:
            continue
        value = drift.psi(reference, drift.histogram(samples))
        results[device.id] = value
        prom.DRIFT_PSI.labels(device.id, f"{model.name}:{model.version}").set(value)
        if value > threshold:
            raise_alert(db, device.id, "drift", "warning",
                        f"Drift en {model.name} v{model.version} sobre {device.name}: "
                        f"PSI={value:.3f} (> {threshold:g})")
        else:
            resolve_alerts(db, device.id, "drift")
    db.commit()
    return results


def flush_latency(db: Session, now: float | None = None) -> int:
    """Guarda en la base de datos los minutos de latencia ya cerrados."""
    rows = hub.drain_buckets(now if now is not None else time.time())
    for device_id, minute, avg, peak, count in rows:
        db.add(LatencyMinute(device_id=device_id, minute=datetime.fromtimestamp(minute, UTC),
                             avg=round(avg, 2), max=round(peak, 2), count=count))
    db.commit()
    return len(rows)


def check_deploy_timeouts(db: Session) -> list[int]:
    """Un despliegue sin confirmación dentro del plazo de la política se da por fallido."""
    timeout = policies.load(db).number("deploy_timeout_s", 120)
    cutoff = utcnow() - timedelta(seconds=timeout)
    expired = []
    for dep in db.query(Deployment).filter_by(status="pending"):
        created = dep.created_at if dep.created_at.tzinfo else dep.created_at.replace(tzinfo=UTC)
        if created < cutoff:
            dep.message = f"Sin confirmación del dispositivo en {timeout:g} s (última etapa: {dep.stage})"
            dep.status, dep.stage, dep.finished_at = "failed", "failed", utcnow()
            raise_alert(db, dep.device_id, "deployment_failed", "critical",
                        f"Despliegue de {dep.model.name} v{dep.model.version} en {dep.device_id} "
                        f"sin respuesta tras {timeout:g} s")
            audit.record(db, "system", "deployment.timeout", "deployment", dep.id, {"timeout_s": timeout})
            hub.broadcast({"type": "deployment",
                           "data": {"id": dep.id, "status": "failed", "stage": "failed"}})
            expired.append(dep.id)
    db.commit()
    return expired


async def run_forever(stop: asyncio.Event) -> None:
    settings = get_settings()
    ticks = 0
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(check_heartbeats, db)
                await asyncio.to_thread(check_deploy_timeouts, db)
                await asyncio.to_thread(flush_latency, db)
                if ticks % max(1, settings.drift_interval_s // 5) == 0:
                    await asyncio.to_thread(check_drift, db)
        except Exception:
            log.exception("Error en tareas periódicas")
        ticks += 1
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5)
