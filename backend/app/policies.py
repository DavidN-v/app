"""Políticas de gobernanza.

Las reglas se guardan en la tabla policies para que un administrador pueda cambiarlas desde
la consola sin reiniciar el sistema; cada cambio queda registrado en la auditoría. Este módulo
las carga y comprueba si un despliegue las cumple antes de enviarlo al dispositivo.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import Device, MLModel, Policy

# Valores iniciales: clave -> (valor, descripción que se muestra en la consola)
DEFAULT_POLICIES: dict[str, tuple[str, str]] = {
    "max_latency_ms": ("100", "Latencia de inferencia máxima antes de alertar (ms)"),
    "max_temp_c": ("75", "Temperatura máxima del dispositivo (°C)"),
    "max_cpu_pct": ("90", "Uso de CPU máximo (%)"),
    "max_ram_pct": ("85", "Uso de RAM máximo (%)"),
    "deploy_timeout_s": ("120", "Segundos sin confirmación antes de dar un despliegue por fallido"),
    "max_drift_psi": ("0.2", "PSI máximo antes de declarar drift"),
    "require_signature": ("true", "Solo se despliegan modelos firmados"),
    "allowed_licenses": ("apache-2.0,mit,agpl-3.0,llama3", "Licencias permitidas (CSV)"),
    "require_online_device": ("true", "El dispositivo destino debe estar en línea"),
}

# Formatos de modelo que puede ejecutar cada tipo de hardware
COMPATIBILITY = {
    "rpi5": {"onnx", "gguf", "tflite"},
    "arduino": {"onnx", "tflite"},
    "esp32": {"tflite"},
}


@dataclass
class PolicySet:
    """Conjunto de políticas activas. Los valores se guardan como texto y estos métodos
    los convierten al tipo que necesita cada regla."""

    values: dict[str, str]

    def number(self, key: str, default: float) -> float:
        """Valor numérico; si falta o no es un número válido se usa el valor por defecto."""
        try:
            return float(self.values[key])
        except (KeyError, ValueError):
            return default

    def flag(self, key: str) -> bool:
        """Valor de sí o no."""
        return self.values.get(key, "false").lower() in ("1", "true", "yes")

    def csv(self, key: str) -> set[str]:
        """Lista de valores separados por comas, en minúsculas."""
        return {v.strip().lower() for v in self.values.get(key, "").split(",") if v.strip()}


def load(db: Session) -> PolicySet:
    """Lee de la base de datos las políticas que están activadas."""
    return PolicySet({p.key: p.value for p in db.query(Policy).filter_by(enabled=True)})


def ensure_defaults(db: Session) -> None:
    """Crea las políticas que todavía no existen sin tocar las que ya modificó el administrador."""
    existing = {p.key for p in db.query(Policy)}
    for key, (value, description) in DEFAULT_POLICIES.items():
        if key not in existing:
            db.add(Policy(key=key, value=value, description=description))
    db.commit()


def deployment_violations(policies: PolicySet, model: MLModel, device: Device) -> list[str]:
    """Devuelve la lista de reglas que incumpliría instalar el modelo en el dispositivo.

    Una lista vacía significa que el despliegue está permitido. Se devuelven todas las
    infracciones a la vez para que el usuario pueda corregirlas de una sola vez.
    """
    violations: list[str] = []
    if model.status not in ("approved", "deployed"):
        violations.append(f"El modelo está en estado '{model.status}'; debe estar aprobado")
    if policies.flag("require_signature") and not model.signature:
        violations.append("El modelo no está firmado (require_signature)")
    allowed = policies.csv("allowed_licenses")
    if allowed and model.license.lower() not in allowed:
        violations.append(f"Licencia '{model.license}' no permitida")
    if policies.flag("require_online_device") and device.status != "online":
        violations.append(f"El dispositivo '{device.id}' no está en línea")
    if model.framework not in COMPATIBILITY.get(device.kind, set()):
        violations.append(f"{device.kind} no puede ejecutar modelos {model.framework}")
    return violations
