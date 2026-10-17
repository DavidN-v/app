VALID_MODEL = {
    "name": "defect-detector",
    "version": "1.0",
    "framework": "onnx",
    "task": "inspección visual",
    "artifact_uri": "http://artifacts.local/defect-1.0.onnx",
    "sha256": "a" * 64,
    "signature": "cosign:sig",
    "license": "apache-2.0",
    "metrics": {"mAP50": 0.9},
}


def register(client, auth, **overrides):
    r = client.post("/api/models", headers=auth("operator"), json={**VALID_MODEL, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_register_starts_as_draft_with_owner(client, auth):
    model = register(client, auth)
    assert model["status"] == "draft"
    assert model["owner"] == "operator"


def test_duplicate_version_rejected(client, auth):
    register(client, auth)
    r = client.post("/api/models", headers=auth("operator"), json=VALID_MODEL)
    assert r.status_code == 409


def test_invalid_sha256_rejected(client, auth):
    r = client.post("/api/models", headers=auth("operator"), json={**VALID_MODEL, "sha256": "xyz"})
    assert r.status_code == 422


def test_approve_by_other_user(client, auth):
    model = register(client, auth)
    r = client.post(f"/api/models/{model['id']}/transition", headers=auth("approver"),
                    json={"to": "approved", "reason": "validado"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == "approver"


def test_separation_of_duties(client, auth):
    # admin registra y luego intenta aprobar su propio modelo
    r = client.post("/api/models", headers=auth("admin"), json=VALID_MODEL)
    model_id = r.json()["id"]
    r = client.post(f"/api/models/{model_id}/transition", headers=auth("admin"),
                    json={"to": "approved"})
    assert r.status_code == 403


def test_operator_cannot_approve(client, auth):
    model = register(client, auth)
    r = client.post(f"/api/models/{model['id']}/transition", headers=auth("operator"),
                    json={"to": "approved"})
    assert r.status_code == 403


def test_retired_is_terminal(client, auth):
    model = register(client, auth)
    url = f"/api/models/{model['id']}/transition"
    assert client.post(url, headers=auth("approver"), json={"to": "retired"}).status_code == 200
    r = client.post(url, headers=auth("approver"), json={"to": "approved"})
    assert r.status_code == 409


def test_cannot_transition_to_deployed_manually(client, auth):
    model = register(client, auth)
    r = client.post(f"/api/models/{model['id']}/transition", headers=auth("approver"),
                    json={"to": "deployed"})
    assert r.status_code == 422


def test_filter_by_status(client, auth):
    register(client, auth)
    drafts = client.get("/api/models?status=draft", headers=auth("viewer")).json()
    assert drafts and all(m["status"] == "draft" for m in drafts)
