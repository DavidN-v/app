import pytest

from app.security import hash_password, verify_password


def test_password_hash_roundtrip():
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "garbage")


def test_login_ok_and_me(client, auth):
    r = client.get("/api/auth/me", headers=auth("approver"))
    assert r.json() == {"username": "approver", "role": "approver"}


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/api/devices", "/api/models", "/api/overview", "/api/alerts"])
def test_endpoints_require_token(client, path):
    assert client.get(path).status_code == 401


def test_invalid_token_rejected(client):
    r = client.get("/api/devices", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_viewer_cannot_register_model(client, auth):
    r = client.post("/api/models", headers=auth("viewer"), json={})
    assert r.status_code == 403


def test_operator_cannot_edit_policies(client, auth):
    r = client.patch("/api/policies/max_temp_c", headers=auth("operator"), json={"value": "99"})
    assert r.status_code == 403


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_metrics_endpoint(client):
    r = client.get("/metrics/")
    assert r.status_code == 200
    assert "edge_mqtt_messages_total" in r.text
