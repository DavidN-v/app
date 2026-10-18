"""Rutas del registro de modelos y de su ciclo de vida."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import MLModel, User, utcnow
from ..schemas import ModelIn, ModelOut, TransitionIn
from ..security import current_user, require_role

router = APIRouter(prefix="/api/models", tags=["models"])

# Un modelo retirado ya no puede cambiar. El estado "deployed" no se asigna a mano: lo pone el
# sistema cuando un dispositivo confirma que lo ha instalado.
TRANSITIONS = {
    "draft": {"approved", "retired"},
    "approved": {"retired"},
    "deployed": {"retired"},
    "retired": set(),
}


@router.get("", response_model=list[ModelOut])
def list_models(status_: str | None = Query(None, alias="status"), db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    q = db.query(MLModel)
    if status_:
        q = q.filter_by(status=status_)
    return q.order_by(MLModel.created_at.desc(), MLModel.id.desc()).all()


@router.get("/{model_id}", response_model=ModelOut)
def get_model(model_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    model = db.get(MLModel, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado")
    return model


@router.post("", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def register_model(body: ModelIn, db: Session = Depends(get_db),
                   user: User = Depends(require_role("operator"))):
    if db.query(MLModel).filter_by(name=body.name, version=body.version).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa versión del modelo ya está registrada")
    model = MLModel(**body.model_dump(), owner=user.username, status="draft")
    db.add(model)
    db.flush()
    audit.record(db, user.username, "model.registered", "model", model.id,
                 {"name": model.name, "version": model.version, "sha256": model.sha256})
    db.commit()
    return model


@router.post("/{model_id}/transition", response_model=ModelOut)
def transition(model_id: int, body: TransitionIn, db: Session = Depends(get_db),
               user: User = Depends(require_role("approver"))):
    model = db.get(MLModel, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado")
    if body.to not in TRANSITIONS[model.status]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Transición no permitida: {model.status} -> {body.to}")
    if body.to == "approved":
        # Separación de funciones: quien registra un modelo no puede aprobarlo él mismo
        if model.owner == user.username:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes aprobar tu propio modelo")
        model.approved_by, model.approved_at = user.username, utcnow()
    previous = model.status
    model.status = body.to
    audit.record(db, user.username, f"model.{body.to}", "model", model.id,
                 {"from": previous, "to": body.to, "reason": body.reason})
    db.commit()
    return model
