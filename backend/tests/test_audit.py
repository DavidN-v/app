from app.models import AuditEntry
from tests.test_models_lifecycle import register


def test_actions_are_audited(client, auth):
    model = register(client, auth)
    client.post(f"/api/models/{model['id']}/transition", headers=auth("approver"),
                json={"to": "approved", "reason": "ok"})
    entries = client.get("/api/audit", headers=auth("approver")).json()
    actions = [e["action"] for e in entries[:2]]
    assert actions == ["model.approved", "model.registered"]
    assert entries[0]["actor"] == "approver"


def test_chain_is_valid(client, auth):
    register(client, auth)
    r = client.get("/api/audit/verify", headers=auth("approver")).json()
    assert r["valid"] is True
    assert r["entries"] > 1


def test_tampering_is_detected(client, auth, db):
    register(client, auth)
    entry = db.query(AuditEntry).order_by(AuditEntry.id.desc()).first()
    entry.actor = "attacker"
    db.commit()
    r = client.get("/api/audit/verify", headers=auth("approver")).json()
    assert r == {"valid": False, "entries": r["entries"], "broken_at": entry.id}


def test_viewer_cannot_read_audit(client, auth):
    assert client.get("/api/audit", headers=auth("viewer")).status_code == 403


def test_blocked_deployment_is_audited(client, auth):
    model = register(client, auth)
    client.post("/api/deployments", headers=auth("operator"),
                json={"model_id": model["id"], "device_id": "rpi5-vision"})
    entries = client.get("/api/audit", headers=auth("approver")).json()
    assert entries[0]["action"] == "deployment.blocked"
    assert entries[0]["details"]["violations"]
