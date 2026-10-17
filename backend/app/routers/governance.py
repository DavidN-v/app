"""Alertas, políticas, auditoría y vista general."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..hub import hub
from ..models import Alert, AuditEntry, Deployment, Device, MLModel, Policy, User
from ..schemas import (
    AlertAction,
    AlertOut,
    AuditOut,
    ChainVerification,
    PolicyOut,
    PolicyUpdate,
)
from ..security import current_user, require_role

router = APIRouter(prefix="/api", tags=["governance"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(status_: str | None = Query(None, alias="status"), limit: int = 100,
                db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = db.query(Alert)
    if status_:
        q = q.filter_by(status=status_)
    return q.order_by(Alert.id.desc()).limit(min(limit, 500)).all()


@router.post("/alerts/{alert_id}/action", response_model=AlertOut)
def act_on_alert(alert_id: int, body: AlertAction, db: Session = Depends(get_db),
                 user: User = Depends(require_role("operator"))):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    if alert.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "La alerta ya está resuelta")
    alert.status, alert.handled_by = body.status, user.username
    audit.record(db, user.username, f"alert.{body.status}", "alert", alert.id)
    db.commit()
    return alert


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(Policy).order_by(Policy.key).all()


@router.patch("/policies/{key}", response_model=PolicyOut)
def update_policy(key: str, body: PolicyUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_role("admin"))):
    policy = db.get(Policy, key)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Política no encontrada")
    before = {"value": policy.value, "enabled": policy.enabled}
    if body.value is not None:
        policy.value = body.value
    if body.enabled is not None:
        policy.enabled = body.enabled
    audit.record(db, user.username, "policy.updated", "policy", key,
                 {"before": before, "after": {"value": policy.value, "enabled": policy.enabled}})
    db.commit()
    return policy


@router.get("/audit", response_model=list[AuditOut])
def list_audit(limit: int = 200, db: Session = Depends(get_db),
               _: User = Depends(require_role("approver"))):
    return db.query(AuditEntry).order_by(AuditEntry.id.desc()).limit(min(limit, 1000)).all()


@router.get("/audit/verify", response_model=ChainVerification)
def verify_audit(db: Session = Depends(get_db), _: User = Depends(require_role("approver"))):
    valid, entries, broken_at = audit.verify_chain(db)
    return ChainVerification(valid=valid, entries=entries, broken_at=broken_at)


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(current_user)):
    devices = db.query(Device).all()
    online = [d for d in devices if d.status == "online"]

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 1) if values else None

    by_status = dict(db.query(MLModel.status, func.count()).group_by(MLModel.status).all())
    return {
        "devices": {"total": len(devices), "online": len(online)},
        "models": {"total": sum(by_status.values()), "by_status": by_status},
        "deployments": {
            "pending": db.query(Deployment).filter_by(status="pending").count(),
            "failed": db.query(Deployment).filter_by(status="failed").count(),
        },
        "alerts_open": db.query(Alert).filter(Alert.status != "resolved").count(),
        "avg": {
            "latency_ms": avg(d.latency_ms for d in online),
            "cpu": avg(d.cpu for d in online),
            "ram": avg(d.ram for d in online),
            "temp": avg(d.temp for d in online),
        },
        "latency_series": {k: v[-120:] for k, v in hub.latency_series().items()},
    }
