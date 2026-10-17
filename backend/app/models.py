"""Modelo de datos: cada clase corresponde a una tabla de la base de datos.

Tablas principales:
- users: usuarios de la consola y su rol.
- devices: dispositivos edge, su último estado conocido y el modelo que tienen instalado.
- models: registro de modelos de IA con su versión, licencia, firma y estado de aprobación.
- deployments: solicitudes de instalación de un modelo en un dispositivo.
- policies: reglas de gobernanza editables (umbrales, licencias permitidas, etc.).
- alerts: incidencias detectadas.
- audit_log: historial encadenado de todas las acciones.
- latency_minutes: latencia media por minuto, para las gráficas de 1 h y 24 h.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """Fecha y hora actual en UTC. Todas las fechas se guardan en UTC para evitar
    confusiones con la zona horaria de cada equipo."""
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # admin | approver | operator | viewer


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))  # rpi5 | arduino | esp32
    role: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="offline")  # online | offline
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Últimas lecturas recibidas; quedan vacías si el dispositivo no tiene ese sensor
    cpu: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    current_model: Mapped["MLModel | None"] = relationship()


class MLModel(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("name", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(32))
    framework: Mapped[str] = mapped_column(String(32))  # onnx | gguf | tflite
    task: Mapped[str] = mapped_column(String(64))
    # Dirección del archivo del modelo y su resumen SHA-256, que el dispositivo comprueba al descargarlo
    artifact_uri: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(64))
    # Métricas de validación; puede incluir el histograma de confianza de referencia para el drift
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    # Ciclo de vida: draft -> approved -> deployed -> retired
    status: Mapped[str] = mapped_column(String(16), default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | succeeded | failed
    # Etapa de la instalación:
    # requested -> downloading -> verifying -> installing -> confirmed | failed
    stage: Mapped[str] = mapped_column(String(16), default="requested")
    requested_by: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model: Mapped[MLModel] = relationship()
    device: Mapped[Device] = relationship()


class Policy(Base):
    __tablename__ = "policies"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(16))  # info | warning | critical
    kind: Mapped[str] = mapped_column(String(32))  # high_cpu, offline, drift, etc.
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | acknowledged | resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Usuario que la atendió, o "system" si se cerró sola al desaparecer la condición
    handled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    # Resumen de la entrada anterior y de esta misma (ver audit.py)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class LatencyMinute(Base):
    """Latencia media y máxima por minuto y dispositivo. Sirve para las gráficas de 1 h y 24 h
    y, al estar en la base de datos, no se pierde si se reinicia la API."""
    __tablename__ = "latency_minutes"
    __table_args__ = (UniqueConstraint("device_id", "minute"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    minute: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    avg: Mapped[float] = mapped_column(Float)
    max: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer)
