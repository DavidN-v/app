"""Rutas de consulta, alta y baja de dispositivos."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Deployment, Device, User
from ..schemas import DeviceIn, DeviceOut
from ..security import current_user, require_role

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Todos los dispositivos con su último estado conocido."""
    return db.query(Device).order_by(Device.created_at, Device.id).all()


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Un dispositivo concreto."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    return device


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(body: DeviceIn, db: Session = Depends(get_db),
                    user: User = Depends(require_role("admin"))):
    """Da de alta un dispositivo. Solo los dispositivos registrados pueden enviar datos."""
    if db.get(Device, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "El dispositivo ya existe")
    device = Device(**body.model_dump())
    db.add(device)
    audit.record(db, user.username, "device.registered", "device", device.id, body.model_dump())
    db.commit()
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def decommission_device(device_id: str, db: Session = Depends(get_db),
                        user: User = Depends(require_role("admin"))):
    """Da de baja un dispositivo; la baja queda registrada en la auditoría."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    # Sus despliegues dependen del dispositivo en la base de datos y se borran con él;
    # el historial completo sigue en la auditoría
    removed = db.query(Deployment).filter_by(device_id=device_id).delete()
    db.delete(device)
    audit.record(db, user.username, "device.decommissioned", "device", device_id,
                 {"deployments_removed": removed})
    db.commit()
