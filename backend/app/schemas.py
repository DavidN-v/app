"""Esquemas de datos de la API.

Definen qué campos se aceptan en cada petición (clases terminadas en In) y qué campos se
devuelven en cada respuesta (terminadas en Out). Pydantic valida los datos automáticamente:
si una petición no cumple el esquema, la API responde con un error 422 que indica el campo.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "approver", "operator", "viewer"]
Framework = Literal["onnx", "gguf", "tflite"]


class ORM(BaseModel):
    """Base para respuestas que se construyen directamente a partir de objetos de la base de datos."""

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    """Respuesta del inicio de sesión."""

    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role


class LoginIn(BaseModel):
    username: str
    password: str


class ModelBrief(ORM):
    """Datos mínimos de un modelo, para mostrarlo dentro de otros objetos."""

    id: int
    name: str
    version: str
    framework: str


class DeviceIn(BaseModel):
    # Identificador en minúsculas, números y guiones: se usa como parte del tema MQTT
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,63}$")
    name: str
    kind: Literal["rpi5", "arduino", "esp32"]
    role: str = ""
    location: str = ""


class DeviceOut(ORM):
    id: str
    name: str
    kind: str
    role: str
    location: str
    status: str
    last_seen: datetime | None
    cpu: float | None
    ram: float | None
    temp: float | None
    latency_ms: float | None
    current_model: ModelBrief | None


class ModelIn(BaseModel):
    """Datos para registrar una versión de un modelo."""

    name: str = Field(min_length=2, max_length=128)
    version: str = Field(min_length=1, max_length=32)
    framework: Framework
    task: str
    artifact_uri: str
    # Resumen SHA-256 en hexadecimal (64 caracteres)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    signature: str | None = None
    license: str
    metrics: dict = {}


class ModelOut(ORM):
    id: int
    name: str
    version: str
    framework: str
    task: str
    artifact_uri: str
    sha256: str
    signature: str | None
    license: str
    owner: str
    metrics: dict
    status: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime


class TransitionIn(BaseModel):
    """Cambio de estado de un modelo, con el motivo que queda en la auditoría."""

    to: Literal["approved", "retired"]
    reason: str = ""


class DeploymentIn(BaseModel):
    model_id: int
    device_id: str


class DeploymentOut(ORM):
    id: int
    model: ModelBrief
    device_id: str
    status: str
    stage: str
    requested_by: str
    message: str
    created_at: datetime
    finished_at: datetime | None


class PolicyOut(ORM):
    key: str
    value: str
    description: str
    enabled: bool


class PolicyUpdate(BaseModel):
    """Cambio de una política; los campos que no se envían se dejan como están."""

    value: str | None = None
    enabled: bool | None = None


class AlertOut(ORM):
    id: int
    device_id: str | None
    severity: str
    kind: str
    message: str
    status: str
    created_at: datetime
    handled_by: str | None


class AlertAction(BaseModel):
    status: Literal["acknowledged", "resolved"]


class AuditOut(ORM):
    id: int
    ts: datetime
    actor: str
    action: str
    entity: str
    entity_id: str
    details: dict
    prev_hash: str
    hash: str


class ChainVerification(BaseModel):
    """Resultado de comprobar la cadena de auditoría."""

    valid: bool
    entries: int
    broken_at: int | None = None
