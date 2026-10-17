"""Registro de auditoría encadenado."""

import hashlib
import json
from datetime import UTC

from sqlalchemy.orm import Session

from .models import AuditEntry, utcnow

# Resumen ficticio que se usa como "anterior" de la primera entrada
GENESIS = "0" * 64


def _digest(prev_hash: str, ts: str, actor: str, action: str, entity: str, entity_id: str,
            details: dict) -> str:
    body = json.dumps(
        [prev_hash, ts, actor, action, entity, entity_id, details], sort_keys=True, default=str
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _ts(value) -> str:
    # SQLite devuelve datetimes sin zona; se normalizan a UTC y precisión de segundos
    # para que el hash sea idéntico en cualquier motor de base de datos.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def record(db: Session, actor: str, action: str, entity: str, entity_id,
           details: dict | None = None) -> AuditEntry:
    last = db.query(AuditEntry).order_by(AuditEntry.id.desc()).first()
    prev_hash = last.hash if last else GENESIS
    ts = utcnow().replace(microsecond=0)
    details = json.loads(json.dumps(details or {}, default=str))
    entry = AuditEntry(
        ts=ts, actor=actor, action=action, entity=entity, entity_id=str(entity_id),
        details=details, prev_hash=prev_hash,
        hash=_digest(prev_hash, _ts(ts), actor, action, entity, str(entity_id), details),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> tuple[bool, int, int | None]:
    prev = GENESIS
    count = 0
    for e in db.query(AuditEntry).order_by(AuditEntry.id):
        count += 1
        expected = _digest(prev, _ts(e.ts), e.actor, e.action, e.entity, e.entity_id, e.details)
        if e.prev_hash != prev or e.hash != expected:
            return False, count, e.id
        prev = e.hash
    return True, count, None
