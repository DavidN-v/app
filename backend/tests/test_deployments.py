from app.models import Device, MLModel
from tests.test_models_lifecycle import register


def approved_model(client, auth, **overrides):
    model = register(client, auth, **overrides)
    r = client.post(f"/api/models/{model['id']}/transition", headers=auth("approver"),
                    json={"to": "approved"})
    assert r.status_code == 200
    return r.json()


def bring_online(mqtt, device_id="rpi5-vision"):
    mqtt(f"edge/{device_id}/telemetry", {"cpu": 10, "ram": 20, "temp": 40})


def test_happy_path_deploy_and_ack(client, auth, mqtt, db):
    model = approved_model(client, auth)
    bring_online(mqtt)
    r = client.post("/api/deployments", headers=auth("operator"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.status_code == 202, r.text
    dep = r.json()
    assert dep["status"] == "pending"

    # Se publicó la orden por MQTT con hash e URL
    device_id, command = client.app.state.bridge.published[-1]
    assert device_id == "rpi5-vision"
    assert command["sha256"] == model["sha256"]
    assert command["deployment_id"] == dep["id"]

    # El dispositivo confirma
    mqtt("edge/rpi5-vision/deploy/ack", {"deployment_id": dep["id"], "status": "succeeded"})
    assert db.get(Device, "rpi5-vision").current_model_id == model["id"]
    assert db.get(MLModel, model["id"]).status == "deployed"


def test_failed_ack_raises_critical_alert(client, auth, mqtt):
    model = approved_model(client, auth)
    bring_online(mqtt)
    dep = client.post("/api/deployments", headers=auth("operator"),
                      json={"model_id": model["id"], "device_id": "rpi5-vision"}).json()
    mqtt("edge/rpi5-vision/deploy/ack",
         {"deployment_id": dep["id"], "status": "failed", "message": "sha256 mismatch"})
    alerts = client.get("/api/alerts", headers=auth("viewer")).json()
    assert any(a["kind"] == "deployment_failed" and a["severity"] == "critical" for a in alerts)


def test_draft_model_is_blocked(client, auth, mqtt):
    model = register(client, auth)
    bring_online(mqtt)
    r = client.post("/api/deployments", headers=auth("operator"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.status_code == 422
    assert any("aprobado" in v for v in r.json()["detail"]["violations"])


def test_unsigned_model_is_blocked(client, auth, mqtt):
    model = approved_model(client, auth, signature=None, version="2.0")
    bring_online(mqtt)
    r = client.post("/api/deployments/check", headers=auth("viewer"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.json()["allowed"] is False
    assert any("firmado" in v for v in r.json()["violations"])


def test_offline_device_is_blocked(client, auth):
    model = approved_model(client, auth)
    r = client.post("/api/deployments", headers=auth("operator"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.status_code == 422
    assert any("en línea" in v for v in r.json()["detail"]["violations"])


def test_incompatible_hardware_is_blocked(client, auth, mqtt):
    model = approved_model(client, auth)  # ONNX
    bring_online(mqtt, "esp32-env")
    r = client.post("/api/deployments/check", headers=auth("viewer"),
                    json={"model_id": model["id"], "device_id": "esp32-env"})
    assert any("esp32 no puede ejecutar" in v for v in r.json()["violations"])


def test_disallowed_license_is_blocked(client, auth, mqtt):
    model = approved_model(client, auth, license="proprietary", version="3.0")
    bring_online(mqtt)
    r = client.post("/api/deployments/check", headers=auth("viewer"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert any("Licencia" in v for v in r.json()["violations"])


def test_disabling_policy_unblocks(client, auth, mqtt):
    model = approved_model(client, auth, signature=None, version="4.0")
    bring_online(mqtt)
    client.patch("/api/policies/require_signature", headers=auth("admin"), json={"enabled": False})
    r = client.post("/api/deployments/check", headers=auth("viewer"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.json() == {"allowed": True, "violations": []}


def test_only_one_pending_per_device(client, auth, mqtt):
    model = approved_model(client, auth)
    bring_online(mqtt)
    body = {"model_id": model["id"], "device_id": "rpi5-vision"}
    assert client.post("/api/deployments", headers=auth("operator"), json=body).status_code == 202
    assert client.post("/api/deployments", headers=auth("operator"), json=body).status_code == 409


def test_ack_from_wrong_device_is_ignored(client, auth, mqtt, db):
    model = approved_model(client, auth)
    bring_online(mqtt)
    dep = client.post("/api/deployments", headers=auth("operator"),
                      json={"model_id": model["id"], "device_id": "rpi5-vision"}).json()
    mqtt("edge/rpi5-genai/deploy/ack", {"deployment_id": dep["id"], "status": "succeeded"})
    deps = client.get("/api/deployments", headers=auth("viewer")).json()
    assert deps[0]["status"] == "pending"
