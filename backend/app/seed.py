"""Datos iniciales: usuarios por rol y, opcionalmente, el laboratorio de demostración."""

import hashlib

from sqlalchemy.orm import Session

from . import audit, policies
from .config import get_settings
from .drift import BINS
from .models import Device, MLModel, User, utcnow
from .security import hash_password

DEMO_DEVICES = [
    ("rpi5-vision", "Raspberry Pi 5 (Visión)", "rpi5", "Visión artificial"),
    ("rpi5-genai", "Raspberry Pi 5 (GenAI)", "rpi5", "Modelo de lenguaje pequeño"),
    ("rpi5-agent", "Raspberry Pi 5 (Agente)", "rpi5", "Agente de telemetría"),
    ("uno-q", "Arduino Uno Q", "arduino", "Detección de objetos"),
    ("ventuno", "Arduino Ventuno", "arduino", "Sensores industriales"),
    ("esp32-env", "ESP32", "esp32", "Regresión ambiental"),
]

# Distribución de confianza de referencia (validación offline): Beta(8, 2), media ≈ 0.8
_REF_HIST = [0.0, 0.0, 0.0004, 0.0033, 0.0158, 0.0507, 0.1261, 0.241, 0.3372, 0.2256]
assert len(_REF_HIST) == len(BINS) - 1

DEMO_MODELS = [
    # name, version, framework, task, license, device, metrics
    ("yolo", "8.1", "onnx", "detección de objetos", "agpl-3.0", "rpi5-vision",
     {"mAP50": 0.87, "reference_confidence_hist": _REF_HIST}),
    ("qwen2.5-0.5b", "q4_k_m", "gguf", "asistente industrial", "apache-2.0", "rpi5-genai",
     {"tokens_per_s": 22.0}),
    ("telemetry-agent", "1.4", "onnx", "clasificación de eventos", "apache-2.0", "rpi5-agent",
     {"f1": 0.91}),
    ("yolo-nano", "8.1-int8", "onnx", "detección de objetos", "agpl-3.0", "uno-q",
     {"mAP50": 0.79, "reference_confidence_hist": _REF_HIST}),
    ("anomaly-ts", "2.0", "tflite", "series temporales", "apache-2.0", "ventuno",
     {"auc": 0.94}),
    ("env-regressor", "1.1", "tflite", "regresión ambiental", "mit", "esp32-env",
     {"mae": 0.42, "r2": 0.93}),
]


def run(db: Session) -> None:
    s = get_settings()
    policies.ensure_defaults(db)
    if db.query(User).count() == 0:
        for username, role, pwd in [("admin", "admin", s.admin_password),
                                    ("approver", "approver", s.approver_password),
                                    ("operator", "operator", s.operator_password),
                                    ("viewer", "viewer", "viewer123")]:
            db.add(User(username=username, role=role, password_hash=hash_password(pwd)))
        db.commit()

    if not s.seed_demo_data or db.query(Device).count():
        return

    for dev_id, name, kind, role in DEMO_DEVICES:
        db.add(Device(id=dev_id, name=name, kind=kind, role=role, location="Laboratorio"))
    db.flush()
    for name, version, fw, task, lic, dev_id, metrics in DEMO_MODELS:
        model = MLModel(
            name=name, version=version, framework=fw, task=task, license=lic, metrics=metrics,
            artifact_uri=f"http://artifacts.local/{name}-{version}.{fw}",
            sha256=hashlib.sha256(f"{name}{version}".encode()).hexdigest(),
            signature=f"cosign:demo:{name}:{version}", owner="operator",
            status="deployed", approved_by="approver", approved_at=utcnow(),
        )
        db.add(model)
        db.flush()
        db.get(Device, dev_id).current_model_id = model.id
        audit.record(db, "system", "model.seeded", "model", model.id, {"device": dev_id})
    # Un modelo pendiente de aprobación para probar el flujo de gobernanza
    db.add(MLModel(
        name="yolo", version="8.2", framework="onnx", task="detección de objetos",
        license="agpl-3.0", metrics={"mAP50": 0.89, "reference_confidence_hist": _REF_HIST},
        artifact_uri="http://artifacts.local/yolo-8.2.onnx",
        sha256=hashlib.sha256(b"yolo8.2").hexdigest(), signature="cosign:demo:yolo:8.2",
        owner="operator", status="draft",
    ))
    db.commit()
