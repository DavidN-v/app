import os

os.environ["EG_DATABASE_URL"] = "sqlite://"
os.environ["EG_MQTT_ENABLED"] = "false"
os.environ["EG_JWT_SECRET"] = "test-secret-with-enough-length-1234"

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ingest  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.hub import hub  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORDS = {"admin": "admin123", "approver": "approver123", "operator": "operator123",
             "viewer": "viewer123"}


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    hub.latency.clear()
    hub.confidence.clear()
    with TestClient(create_app(start_background=False)) as c:
        yield c


@pytest.fixture
def db(client):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def auth(client):
    cache: dict[str, dict] = {}

    def headers(username: str = "admin") -> dict:
        if username not in cache:
            r = client.post("/api/auth/login",
                            json={"username": username, "password": PASSWORDS[username]})
            assert r.status_code == 200, r.text
            cache[username] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[username]

    return headers


@pytest.fixture
def mqtt(db):
    """Simula la llegada de un mensaje MQTT al ingestor."""

    def send(topic: str, payload, retained: bool = False) -> None:
        raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        ingest.handle(db, topic, raw, retained=retained)
        db.expire_all()

    return send
