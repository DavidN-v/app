from sqlalchemy.orm import Session

from . import prom
from .hub import hub
from .models import Alert


def raise_alert(db: Session, device_id: str | None, kind: str, severity: str, message: str
                ) -> Alert | None:
    """Crea una alerta salvo que ya exista una abierta del mismo tipo para el mismo
    dispositivo (deduplicación: evita inundar al operador con la misma condición)."""
    open_same = (
        db.query(Alert)
        .filter(Alert.device_id == device_id, Alert.kind == kind, Alert.status != "resolved")
        .first()
    )
    if open_same:
        return None
    alert = Alert(device_id=device_id, kind=kind, severity=severity, message=message)
    db.add(alert)
    db.flush()
    prom.ALERTS_RAISED.labels(kind, severity).inc()
    hub.broadcast({
        "type": "alert",
        "data": {"id": alert.id, "device_id": device_id, "kind": kind, "severity": severity,
                 "message": message, "status": "open",
                 "created_at": alert.created_at.isoformat()},
    })
    return alert
