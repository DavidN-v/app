import hashlib
import json
from pathlib import Path

import pytest

from edge_agent import system
from edge_agent.agent import EdgeAgent
from edge_agent.deployer import ModelStore, sha256_of

ARTIFACT = b"fake-onnx-weights" * 1000


class FakeClient:
    def __init__(self):
        self.messages: list[tuple[str, str, int, bool]] = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.messages.append((topic, payload, qos, retain))

    def subscribe(self, topic, qos=0):
        self.subscribed = topic


@pytest.fixture
def artifact(tmp_path) -> Path:
    path = tmp_path / "source.onnx"
    path.write_bytes(ARTIFACT)
    return path


def command(artifact: Path, version="1.0", sha=None) -> dict:
    return {"deployment_id": 7, "model": "yolo", "version": version, "framework": "onnx",
            "url": f"file://{artifact}", "sha256": sha or hashlib.sha256(ARTIFACT).hexdigest()}


def test_install_verifies_and_updates_manifest(tmp_path, artifact):
    store = ModelStore(tmp_path / "models")
    result = store.install(command(artifact))
    assert result.ok, result.message
    assert sha256_of(result.path) == hashlib.sha256(ARTIFACT).hexdigest()
    assert store.manifest()["current"]["version"] == "1.0"


def test_hash_mismatch_keeps_previous_model(tmp_path, artifact):
    store = ModelStore(tmp_path / "models")
    store.install(command(artifact))
    result = store.install(command(artifact, version="2.0", sha="0" * 64))
    assert not result.ok
    assert "sha256" in result.message
    assert store.manifest()["current"]["version"] == "1.0"
    assert not list((tmp_path / "models").glob("*.part")), "no deben quedar temporales"
    assert not (tmp_path / "models" / "yolo-2.0.onnx").exists()


def test_download_error_is_reported(tmp_path):
    store = ModelStore(tmp_path / "models")
    result = store.install({**command(tmp_path / "missing.onnx"), "url": "ftp://nope"})
    assert not result.ok
    assert "no soportado" in result.message


def test_rollback(tmp_path, artifact):
    store = ModelStore(tmp_path / "models")
    store.install(command(artifact, "1.0"))
    store.install(command(artifact, "2.0"))
    result = store.rollback()
    assert result.ok
    assert store.manifest()["current"]["version"] == "1.0"
    assert store.manifest()["previous"]["version"] == "2.0"


def test_rollback_without_history(tmp_path):
    assert not ModelStore(tmp_path).rollback().ok


def test_agent_acks_successful_deploy(tmp_path, artifact):
    client = FakeClient()
    agent = EdgeAgent("rpi5-vision", client, ModelStore(tmp_path / "m"))
    ack = agent.handle_deploy(json.dumps(command(artifact)).encode())
    assert ack == {"deployment_id": 7, "status": "succeeded", "message": "yolo v1.0 instalado"}
    topic, payload, qos, _ = client.messages[-1]
    assert topic == "edge/rpi5-vision/deploy/ack"
    assert qos == 1
    assert json.loads(payload)["status"] == "succeeded"


def test_agent_reports_each_stage(tmp_path, artifact):
    client = FakeClient()
    agent = EdgeAgent("rpi5-vision", client, ModelStore(tmp_path / "m"))
    agent.handle_deploy(json.dumps(command(artifact)).encode())
    stages = [json.loads(p)["stage"] for t, p, *_ in client.messages if t.endswith("/deploy/progress")]
    assert stages == ["downloading", "verifying", "installing"]


def test_hash_failure_stops_before_installing(tmp_path, artifact):
    client = FakeClient()
    agent = EdgeAgent("rpi5-vision", client, ModelStore(tmp_path / "m"))
    agent.handle_deploy(json.dumps(command(artifact, sha="f" * 64)).encode())
    stages = [json.loads(p)["stage"] for t, p, *_ in client.messages if t.endswith("/deploy/progress")]
    assert stages == ["downloading", "verifying"]


def test_agent_acks_failed_deploy(tmp_path, artifact):
    client = FakeClient()
    agent = EdgeAgent("rpi5-vision", client, ModelStore(tmp_path / "m"))
    ack = agent.handle_deploy(json.dumps(command(artifact, sha="f" * 64)).encode())
    assert ack["status"] == "failed"


def test_agent_ignores_malformed_command(tmp_path):
    client = FakeClient()
    agent = EdgeAgent("x", client, ModelStore(tmp_path))
    assert agent.handle_deploy(b"{bad") == {}
    assert client.messages == []


def test_track_inference_publishes_latency(tmp_path):
    client = FakeClient()
    agent = EdgeAgent("rpi5-vision", client, ModelStore(tmp_path))
    with agent.track_inference("yolo", "8.1") as trace:
        trace.confidence = 0.93
    topic, payload, *_ = client.messages[-1]
    data = json.loads(payload)
    assert topic == "edge/rpi5-vision/inference"
    assert data["confidence"] == 0.93
    assert data["latency_ms"] >= 0


def test_on_connect_announces_online(tmp_path):
    client = FakeClient()
    agent = EdgeAgent("esp", client, ModelStore(tmp_path))
    agent.on_connect(client, None, None, 0, None)
    assert client.subscribed == "edge/esp/deploy"
    assert client.messages[-1] == ("edge/esp/status", "online", 1, True)


def test_system_collect_shape():
    data = system.collect()
    assert set(data) == {"cpu", "ram", "temp", "disk"}
    assert 0 <= data["ram"] <= 100
