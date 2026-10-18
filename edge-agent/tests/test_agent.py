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


def test_board_meter_measures_against_emulated_board():
    procs = [[(1, 10.0, 512 * 1024 * 1024), (2, 5.0, 512 * 1024 * 1024)]]
    clock = iter([100.0, 102.0])
    meter = system.BoardMeter(cpus=4, ram_mb=4096, processes=lambda: iter(procs[0]),
                              clock=lambda: next(clock))
    assert meter.sample() == (0.0, 25.0)  # primera muestra: sin intervalo todavía
    # En 2 s el proceso 1 usó 3 s de CPU y aparece un proceso 3 nuevo: 3 / (2 * 4) = 37.5 %
    procs[0] = [(1, 13.0, 512 * 1024 * 1024), (2, 5.0, 512 * 1024 * 1024), (3, 50.0, 0)]
    assert meter.sample() == (37.5, 25.0)


def test_loader_receives_the_installed_model(tmp_path, artifact):
    loaded = []
    agent = EdgeAgent("rpi5-vision", FakeClient(), ModelStore(tmp_path / "m"),
                      loader=lambda cmd, path: loaded.append((cmd["version"], path.exists())))
    ack = agent.handle_deploy(json.dumps(command(artifact)).encode())
    assert ack["status"] == "succeeded"
    assert loaded == [("1.0", True)]


def test_loader_failure_reverts_and_reports_failed(tmp_path, artifact):
    def broken(cmd, path):
        raise RuntimeError("formato no soportado")

    store = ModelStore(tmp_path / "m")
    agent = EdgeAgent("rpi5-vision", FakeClient(), store, loader=broken)
    ack = agent.handle_deploy(json.dumps(command(artifact)).encode())
    assert ack["status"] == "failed"
    assert "formato no soportado" in ack["message"]
    assert store.manifest()["current"] is None  # sigue en marcha el modelo anterior


def test_connection_reads_credentials_and_tls_from_env(monkeypatch):
    from edge_agent import connection

    monkeypatch.setenv("EDGE_MQTT_TLS", "1")
    assert connection.tls_enabled()
    monkeypatch.setenv("EDGE_MQTT_TLS", "0")
    client = connection.create_client("esp32-env")
    assert client is not None
