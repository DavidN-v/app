"""Creación y cierre de alertas."""

from sqlalchemy.orm import Session

from . import prom
from .hub import hub
from .models import Alert


def raise_alert(db: Session, device_id: str | None, kind: str, severity: str, message: str
                ) -> Alert | None:
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


def resolve_alerts(db: Session, device_id: str | None, kind: str) -> int:
    open_alerts = (
        db.query(Alert)
        .filter(Alert.device_id == device_id, Alert.kind == kind, Alert.status != "resolved")
        .all()
    )
    for alert in open_alerts:
        alert.status, alert.handled_by = "resolved", "system"
    if open_alerts:
        hub.broadcast({"type": "alert_resolved", "data": {
            "ids": [a.id for a in open_alerts], "device_id": device_id, "kind": kind}})
    return len(open_alerts)
