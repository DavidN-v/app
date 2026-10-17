from app.models import AuditEntry, Deployment, Device

NEW = {"id": "rpi5-taller", "name": "Raspberry Pi 5 (Taller)", "kind": "rpi5", "role": "Visión",
       "location": "Taller"}


def test_admin_registers_device_and_it_is_audited(client, auth, db):
    r = client.post("/api/devices", headers=auth("admin"), json=NEW)
    assert r.status_code == 201
    assert r.json()["status"] == "offline"
    assert db.query(AuditEntry).filter_by(action="device.registered", entity_id="rpi5-taller").count() == 1


def test_only_admin_can_register(client, auth):
    assert client.post("/api/devices", headers=auth("operator"), json=NEW).status_code == 403


def test_device_id_must_be_valid_for_mqtt(client, auth):
    r = client.post("/api/devices", headers=auth("admin"), json={**NEW, "id": "Mi Placa/1"})
    assert r.status_code == 422


def test_duplicate_device_is_rejected(client, auth):
    client.post("/api/devices", headers=auth("admin"), json=NEW)
    assert client.post("/api/devices", headers=auth("admin"), json=NEW).status_code == 409


def test_registered_device_is_accepted_by_ingest(client, auth, mqtt, db):
    client.post("/api/devices", headers=auth("admin"), json=NEW)
    mqtt("edge/rpi5-taller/telemetry", {"cpu": 12, "ram": 30, "temp": 48})
    assert db.get(Device, "rpi5-taller").status == "online"


def test_decommission_removes_device_with_deployment_history(client, auth, db):
    db.add(Deployment(model_id=1, device_id="uno-q", requested_by="operator", status="succeeded"))
    db.commit()
    assert client.delete("/api/devices/uno-q", headers=auth("admin")).status_code == 204
    db.expire_all()
    assert db.get(Device, "uno-q") is None
    assert db.query(Deployment).filter_by(device_id="uno-q").count() == 0
    entry = db.query(AuditEntry).filter_by(action="device.decommissioned").one()
    assert entry.details == {"deployments_removed": 1}
