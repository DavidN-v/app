"""Procesamiento de los mensajes que envían los dispositivos por MQTT.

Cada dispositivo publica en temas con la forma edge/{id}/{tipo}:
  edge/{id}/telemetry        {"cpu": 18.2, "ram": 42.0, "temp": 51.3}
  edge/{id}/inference        {"model": "yolo", "version": "8.1", "latency_ms": 28, "confidence": 0.92}
  edge/{id}/status           "online" | "offline"
  edge/{id}/deploy/progress  {"deployment_id": 3, "stage": "downloading" | "verifying" | "installing"}
  edge/{id}/deploy/ack       {"deployment_id": 3, "status": "succeeded" | "failed", "message": ""}

El mensaje "offline" lo publica el propio broker cuando un dispositivo se desconecta sin
avisar (es el "último mensaje" que el dispositivo deja registrado al conectarse).

Con cada mensaje se actualiza el estado del dispositivo, se comprueban los umbrales de las
políticas para abrir o cerrar alertas y se reenvía el dato a la consola en tiempo real.
"""

import json
import logging

from sqlalchemy.orm import Session

from . import audit, policies, prom
from .alerting import raise_alert, resolve_alerts
from .hub import hub
from .models import Deployment, Device, utcnow

log = logging.getLogger(__name__)

# Una alerta de umbral se cierra sola cuando el valor baja del 90 % del límite.
# El margen evita que una métrica que ronda el límite abra y cierre alertas sin parar.
HYSTERESIS = 0.9
# Número de inferencias recientes con las que se calcula la latencia media
LATENCY_WINDOW = 10


def _threshold(db: Session, device: Device, kind: str, value: float, limit: float,
               severity: str, message: str) -> None:
    """Abre una alerta si el valor supera el límite y la cierra si vuelve a estar por debajo del margen."""
    if value > limit:
        raise_alert(db, device.id, kind, severity, message)
    elif value <= limit * HYSTERESIS:
        resolve_alerts(db, device.id, kind)


def handle(db: Session, topic: str, payload: bytes, retained: bool = False) -> None:
    """Punto de entrada: identifica el dispositivo y el tipo de mensaje y lo envía a su función.

    Un mensaje mal formado se descarta y se deja constancia en el registro, sin detener el sistema.
    """
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "edge":
        return
    device_id, kind = parts[1], "/".join(parts[2:])
    prom.MQTT_MESSAGES.labels(kind).inc()

    device = db.get(Device, device_id)
    if device is None:
        # Un dispositivo que no está dado de alta nunca se acepta sin avisar
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
    """Marca el dispositivo como conectado; si antes estaba desconectado, avisa a la consola."""
    was_offline = device.status != "online"
    device.status = "online"
    device.last_seen = utcnow()
    prom.DEVICE_UP.labels(device.id).set(1)
    if was_offline:
        hub.broadcast({"type": "device_status", "data": {"id": device.id, "status": "online"}})
        # La condición desapareció: se cierran solas las alertas de desconexión
        resolve_alerts(db, device.id, "offline")


def _on_status(db: Session, device: Device, status: str, retained: bool = False) -> None:
    """Cambio de estado anunciado por el dispositivo o por el broker en su nombre."""
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
    """Lectura periódica de CPU, RAM y temperatura: se guarda y se compara con las políticas."""
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
    if device.temp is not None:
        _threshold(db, device, "high_temperature", device.temp, max_temp, "critical",
                   f"Temperatura alta en {device.name}: {device.temp:.1f} °C (> {max_temp:g})")
    else:
        # Sin sensor ya no hay lectura que sostenga una alerta de temperatura anterior
        resolve_alerts(db, device.id, "high_temperature")
    max_cpu = rules.number("max_cpu_pct", 90)
    _threshold(db, device, "high_cpu", device.cpu, max_cpu, "warning",
               f"CPU alta en {device.name}: {device.cpu:.0f}% (> {max_cpu:g}%)")
    max_ram = rules.number("max_ram_pct", 85)
    _threshold(db, device, "high_ram", device.ram, max_ram, "warning",
               f"RAM alta en {device.name}: {device.ram:.0f}% (> {max_ram:g}%)")

    hub.broadcast({"type": "telemetry", "data": {
        "id": device.id, "cpu": device.cpu, "ram": device.ram, "temp": device.temp,
        "ts": device.last_seen.isoformat(),
    }})


def _on_inference(db: Session, device: Device, data: dict) -> None:
    """Resultado de una inferencia: latencia, confianza y modelo que la ha realizado."""
    latency = float(data["latency_ms"])
    model_label = f"{data.get('model', 'unknown')}:{data.get('version', '?')}"
    device.latency_ms = latency
    _mark_online(db, device)
    hub.record_latency(device.id, latency)
    prom.INFERENCE_LATENCY.labels(device.id, model_label).set(latency)
    prom.INFERENCES.labels(device.id, model_label).inc()
    if (conf := data.get("confidence")) is not None:
        hub.record_confidence(device.id, float(conf), data.get("model"))

    max_latency = policies.load(db).number("max_latency_ms", 100)
    avg = hub.recent_latency(device.id, LATENCY_WINDOW)
    _threshold(db, device, "high_latency", avg, max_latency, "warning",
               f"Latencia elevada en {device.name}: media {avg:.0f} ms en las últimas "
               f"{LATENCY_WINDOW} inferencias (> {max_latency:g})")
    _check_model(db, device, data)

    hub.broadcast({"type": "inference", "data": {
        "id": device.id, "latency_ms": latency, "confidence": conf, "model": model_label,
    }})


def _check_model(db: Session, device: Device, data: dict) -> None:
    """Comprueba que el dispositivo ejecuta el modelo que figura en el registro.

    Si no coincide, alguien ha instalado un modelo sin pasar por el proceso de aprobación,
    lo cual es justo lo que la gobernanza debe detectar.
    """
    reported, version = data.get("model"), data.get("version")
    current = device.current_model
    if not reported or current is None:
        return
    if reported != current.name or (version is not None and str(version) != current.version):
        raise_alert(db, device.id, "model_mismatch", "critical",
                    f"{device.name} ejecuta {reported}:{version or '?'}, pero el registro indica "
                    f"{current.name}:{current.version}")
    else:
        resolve_alerts(db, device.id, "model_mismatch")


PROGRESS_STAGES = ("downloading", "verifying", "installing")


def _on_deploy_progress(db: Session, device: Device, data: dict) -> None:
    """Avance de una instalación en curso (descarga, verificación, instalación)."""
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
    """Respuesta final del dispositivo a una orden de despliegue: éxito o fallo."""
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
        # El drift medido era del modelo anterior
        resolve_alerts(db, device.id, "drift")
    else:
        dep.status = "failed"
        dep.stage = "failed"
        raise_alert(db, device.id, "deployment_failed", "critical",
                    f"Falló el despliegue de {dep.model.name} v{dep.model.version}: {dep.message}")
    audit.record(db, f"device:{device.id}", f"deployment.{dep.status}", "deployment", dep.id,
                 {"model_id": dep.model_id, "message": dep.message})
    hub.broadcast({"type": "deployment", "data": {"id": dep.id, "status": dep.status, "stage": dep.stage}})
