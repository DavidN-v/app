"""Rutas para solicitar y consultar despliegues de modelos en los dispositivos."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import audit, policies
from ..db import get_db
from ..models import Deployment, Device, MLModel, User
from ..schemas import DeploymentIn, DeploymentOut
from ..security import current_user, require_role

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


@router.get("", response_model=list[DeploymentOut])
def list_deployments(limit: int = 100, db: Session = Depends(get_db),
                     _: User = Depends(current_user)):
    return db.query(Deployment).order_by(Deployment.id.desc()).limit(min(limit, 500)).all()


@router.post("/check")
def check(body: DeploymentIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    model, device = _load(db, body)
    violations = policies.deployment_violations(policies.load(db), model, device)
    return {"allowed": not violations, "violations": violations}


@router.post("", response_model=DeploymentOut, status_code=status.HTTP_202_ACCEPTED)
def create_deployment(body: DeploymentIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_role("operator"))):
    model, device = _load(db, body)
    violations = policies.deployment_violations(policies.load(db), model, device)
    if violations:
        audit.record(db, user.username, "deployment.blocked", "model", model.id,
                     {"device_id": device.id, "violations": violations})
        db.commit()
        raise HTTPException(422,
                            {"message": "Bloqueado por políticas", "violations": violations})
    if db.query(Deployment).filter_by(device_id=device.id, status="pending").first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un despliegue pendiente en ese dispositivo")

    dep = Deployment(model_id=model.id, device_id=device.id, requested_by=user.username)
    db.add(dep)
    db.flush()
    audit.record(db, user.username, "deployment.requested", "deployment", dep.id,
                 {"model_id": model.id, "device_id": device.id})
    db.commit()

    request.app.state.bridge.publish_deploy(device.id, {
        "deployment_id": dep.id,
        "model": model.name,
        "version": model.version,
        "framework": model.framework,
        "url": model.artifact_uri,
        "sha256": model.sha256,
        "signature": model.signature,
    })
    return dep


def _load(db: Session, body: DeploymentIn) -> tuple[MLModel, Device]:
    model = db.get(MLModel, body.model_id)
    device = db.get(Device, body.device_id)
    if model is None or device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo o dispositivo no encontrado")
    return model, device
