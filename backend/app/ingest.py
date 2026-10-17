"""Procesa los mensajes MQTT de los dispositivos.

Tópicos:
  edge/{id}/telemetry    {"cpu": 18.2, "ram": 42.0, "temp": 51.3}
  edge/{id}/inference    {"model": "yolo", "version": "8.1", "latency_ms": 28, "confidence": 0.92}
  edge/{id}/status       "online" | "offline"   (LWT)
  edge/{id}/deploy/progress {"deployment_id": 3, "stage": "downloading" | "verifying" | "installing"}
  edge/{id}/deploy/ack   {"deployment_id": 3, "status": "succeeded" | "failed", "message": ""}
"""

import json
import logging

from sqlalchemy.orm import Session

from . import audit, policies, prom
from .alerting import raise_alert
from .hub import hub
from .models import Alert, Deployment, Device, utcnow

log = logging.getLogger(__name__)


def handle(db: Session, topic: str, payload: bytes, retained: bool = False) -> None:
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "edge":
        return
    device_id, kind = parts[1], "/".join(parts[2:])
    prom.MQTT_MESSAGES.labels(kind).inc()

    device = db.get(Device, device_id)
    if device is None:
        # Gobernanza: un dispositivo no registrado nunca se acepta en silencio.
        raise_alert(db, device_id, "unregistered_device", "warning",
                    f"Mensaje de dispositivo no registrado '{device_id}' en {topic}")
        db.commit()
        return

    try:
        if kind == "status":
            _on_status(db, device, payload.decode().strip(), retained)
        else:
            data = json.loads(payload)
            if kind == "telemetry":
                _on_telemetry(db, device, data)
            elif kind == "inference":
                _on_inference(db, device, data)
            elif kind == "deploy/progress":
                _on_deploy_progress(db, device, data)
            elif kind == "deploy/ack":
                _on_deploy_ack(db, device, data)
        db.commit()
    except (ValueError, KeyError, TypeError) as exc:
        db.rollback()
        log.warning("Payload inválido en %s: %s", topic, exc)


def _mark_online(db: Session, device: Device) -> None:
    was_offline = device.status != "online"
    device.status = "online"
    device.last_seen = utcnow()
    prom.DEVICE_UP.labels(device.id).set(1)
    if was_offline:
        hub.broadcast({"type": "device_status", "data": {"id": device.id, "status": "online"}})
        # La condición desapareció: se cierran solas las alertas de desconexión
        db.query(Alert).filter(
            Alert.device_id == device.id, Alert.kind == "offline", Alert.status != "resolved"
        ).update({"status": "resolved", "handled_by": "system"})


def _on_status(db: Session, device: Device, status: str, retained: bool = False) -> None:
    if status == "online":
        _mark_online(db, device)
    elif status == "offline":
        device.status = "offline"
        prom.DEVICE_UP.labels(device.id).set(0)
        hub.broadcast({"type": "device_status", "data": {"id": device.id, "status": "offline"}})
        # Un LWT retenido que el broker reenvía al reconectar la API es historia, no un evento nuevo
        if not retained:
            raise_alert(db, device.id, "offline", "warning", f"{device.name} se desconectó")


def _on_telemetry(db: Session, device: Device, data: dict) -> None:
    device.cpu = float(data["cpu"])
    device.ram = float(data["ram"])
    device.temp = float(data["temp"]) if data.get("temp") is not None else None
    _mark_online(db, device)
    prom.DEVICE_CPU.labels(device.id).set(device.cpu)
    prom.DEVICE_RAM.labels(device.id).set(device.ram)
    if device.temp is not None:
        prom.DEVICE_TEMP.labels(device.id).set(device.temp)

    rules = policies.load(db)
    max_temp = rules.number("max_temp_c", 75)
    if device.temp is not None and device.temp > max_temp:
        raise_alert(db, device.id, "high_temperature", "critical",
                    f"Temperatura alta en {device.name}: {device.temp:.1f} °C (> {max_temp:g})")
    max_cpu = rules.number("max_cpu_pct", 90)
    if device.cpu > max_cpu:
        raise_alert(db, device.id, "high_cpu", "warning",
                    f"CPU alta en {device.name}: {device.cpu:.0f}% (> {max_cpu:g}%)")

    max_ram = rules.number("max_ram_pct", 85)
    if device.ram > max_ram:
        raise_alert(db, device.id, "high_ram", "warning",
                    f"RAM alta en {device.name}: {device.ram:.0f}% (> {max_ram:g}%)")

    hub.broadcast({"type": "telemetry", "data": {
        "id": device.id, "cpu": device.cpu, "ram": device.ram, "temp": device.temp,
        "ts": device.last_seen.isoformat(),
    }})


def _on_inference(db: Session, device: Device, data: dict) -> None:
    latency = float(data["latency_ms"])
    model_label = f"{data.get('model', 'unknown')}:{data.get('version', '?')}"
    device.latency_ms = latency
    _mark_online(db, device)
    hub.record_latency(device.id, latency)
    prom.INFERENCE_LATENCY.labels(device.id, model_label).set(latency)
    prom.INFERENCES.labels(device.id, model_label).inc()
    if (conf := data.get("confidence")) is not None:
        hub.record_confidence(device.id, float(conf))

    max_latency = policies.load(db).number("max_latency_ms", 100)
    if latency > max_latency:
        raise_alert(db, device.id, "high_latency", "warning",
                    f"Latencia elevada en {device.name}: {latency:.0f} ms (> {max_latency:g})")

    hub.broadcast({"type": "inference", "data": {
        "id": device.id, "latency_ms": latency, "confidence": conf, "model": model_label,
    }})


PROGRESS_STAGES = ("downloading", "verifying", "installing")


def _on_deploy_progress(db: Session, device: Device, data: dict) -> None:
    stage = str(data["stage"])
    dep = db.get(Deployment, int(data["deployment_id"]))
    if stage not in PROGRESS_STAGES or dep is None or dep.device_id != device.id or dep.status != "pending":
        return
    # Las etapas solo avanzan: un mensaje atrasado no hace retroceder la barra
    order = ("requested", *PROGRESS_STAGES)
    if order.index(stage) > order.index(dep.stage if dep.stage in order else "requested"):
        dep.stage = stage
        hub.broadcast({"type": "deployment", "data": {"id": dep.id, "status": dep.status, "stage": stage}})


def _on_deploy_ack(db: Session, device: Device, data: dict) -> None:
    dep = db.get(Deployment, int(data["deployment_id"]))
    if dep is None or dep.device_id != device.id or dep.status != "pending":
        return
    dep.finished_at = utcnow()
    dep.message = str(data.get("message", ""))
    if data.get("status") == "succeeded":
        dep.status = "succeeded"
        dep.stage = "confirmed"
        device.current_model_id = dep.model_id
        if dep.model.status == "approved":
            dep.model.status = "deployed"
    else:
        dep.status = "failed"
        dep.stage = "failed"
        raise_alert(db, device.id, "deployment_failed", "critical",
                    f"Falló el despliegue de {dep.model.name} v{dep.model.version}: {dep.message}")
    audit.record(db, f"device:{device.id}", f"deployment.{dep.status}", "deployment", dep.id,
                 {"model_id": dep.model_id, "message": dep.message})
    hub.broadcast({"type": "deployment", "data": {"id": dep.id, "status": dep.status, "stage": dep.stage}})
