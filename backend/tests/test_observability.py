import random
from datetime import timedelta

from app import jobs
from app.drift import histogram, psi
from app.models import Alert, Device, utcnow


def open_alerts(db, kind):
    return db.query(Alert).filter_by(kind=kind, status="open").all()


def test_telemetry_updates_device(client, auth, mqtt):
    mqtt("edge/rpi5-vision/telemetry", {"cpu": 18.5, "ram": 42, "temp": 51})
    device = client.get("/api/devices/rpi5-vision", headers=auth("viewer")).json()
    assert device["status"] == "online"
    assert device["cpu"] == 18.5
    assert device["current_model"]["name"] == "yolo"


def test_high_temperature_alert_is_deduplicated(mqtt, db):
    for _ in range(5):
        mqtt("edge/rpi5-genai/telemetry", {"cpu": 30, "ram": 60, "temp": 82})
    alerts = open_alerts(db, "high_temperature")
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


def test_threshold_follows_policy(client, auth, mqtt, db):
    client.patch("/api/policies/max_temp_c", headers=auth("admin"), json={"value": "90"})
    mqtt("edge/rpi5-genai/telemetry", {"cpu": 30, "ram": 60, "temp": 82})
    assert open_alerts(db, "high_temperature") == []


def test_high_latency_alert(mqtt, db):
    mqtt("edge/ventuno/inference", {"model": "anomaly-ts", "version": "2.0", "latency_ms": 250})
    assert len(open_alerts(db, "high_latency")) == 1


def test_unregistered_device_raises_alert(mqtt, db):
    mqtt("edge/rogue-01/telemetry", {"cpu": 1, "ram": 1, "temp": 1})
    assert db.get(Device, "rogue-01") is None
    assert len(open_alerts(db, "unregistered_device")) == 1


def test_malformed_payload_is_ignored(mqtt, db):
    mqtt("edge/rpi5-vision/telemetry", "{not json")
    mqtt("edge/rpi5-vision/telemetry", {"ram": 3})  # falta cpu
    assert db.get(Device, "rpi5-vision").status == "offline"


def test_lwt_offline(mqtt, db):
    mqtt("edge/esp32-env/status", "online")
    assert db.get(Device, "esp32-env").status == "online"
    mqtt("edge/esp32-env/status", "offline")
    assert db.get(Device, "esp32-env").status == "offline"
    assert len(open_alerts(db, "offline")) == 1


def test_retained_offline_does_not_alert(mqtt, db):
    mqtt("edge/esp32-env/status", "offline", retained=True)
    assert db.get(Device, "esp32-env").status == "offline"
    assert open_alerts(db, "offline") == []


def test_offline_alert_auto_resolves_on_reconnect(mqtt, db):
    mqtt("edge/esp32-env/status", "online")
    mqtt("edge/esp32-env/status", "offline")
    assert len(open_alerts(db, "offline")) == 1
    mqtt("edge/esp32-env/telemetry", {"cpu": 1, "ram": 1, "temp": 30})
    alert = db.query(Alert).filter_by(kind="offline").one()
    assert (alert.status, alert.handled_by) == ("resolved", "system")


def test_heartbeat_watchdog(mqtt, db):
    mqtt("edge/uno-q/telemetry", {"cpu": 8, "ram": 18, "temp": 39})
    device = db.get(Device, "uno-q")
    device.last_seen = utcnow() - timedelta(minutes=5)
    db.commit()
    assert jobs.check_heartbeats(db) == ["uno-q"]
    assert db.get(Device, "uno-q").status == "offline"


def test_alert_acknowledge_and_resolve(client, auth, mqtt):
    mqtt("edge/rpi5-genai/telemetry", {"cpu": 30, "ram": 60, "temp": 82})
    alert = client.get("/api/alerts?status=open", headers=auth("viewer")).json()[0]
    url = f"/api/alerts/{alert['id']}/action"
    r = client.post(url, headers=auth("operator"), json={"status": "acknowledged"})
    assert r.json()["handled_by"] == "operator"
    assert client.post(url, headers=auth("operator"), json={"status": "resolved"}).status_code == 200
    assert client.post(url, headers=auth("operator"), json={"status": "resolved"}).status_code == 409


def test_overview_aggregates(client, auth, mqtt):
    mqtt("edge/rpi5-vision/telemetry", {"cpu": 20, "ram": 40, "temp": 50})
    mqtt("edge/esp32-env/telemetry", {"cpu": 10, "ram": 20, "temp": 30})
    mqtt("edge/rpi5-vision/inference", {"model": "yolo", "version": "8.1", "latency_ms": 28})
    data = client.get("/api/overview", headers=auth("viewer")).json()
    assert data["devices"] == {"total": 6, "online": 2}
    assert data["avg"]["cpu"] == 15.0
    assert data["models"]["by_status"]["deployed"] == 6
    assert data["latency_series"]["rpi5-vision"][0][1] == 28


# --- Drift ---------------------------------------------------------------

def test_psi_identical_is_zero():
    dist = [0.1] * 10
    assert psi(dist, dist) == 0


def test_psi_detects_shift():
    rng = random.Random(1)
    reference = histogram([rng.uniform(0.7, 1.0) for _ in range(1000)])
    shifted = histogram([rng.uniform(0.2, 0.6) for _ in range(1000)])
    assert psi(reference, shifted) > 0.2


def test_histogram_normalized_and_handles_edges():
    h = histogram([0.0, 0.5, 1.0])
    assert abs(sum(h) - 1) < 1e-9
    assert h[0] == h[5] == h[9] == 1 / 3


def test_drift_job_raises_alert(mqtt, db):
    rng = random.Random(7)
    for _ in range(80):  # el modelo empieza a dudar: confianzas bajas
        mqtt("edge/rpi5-vision/inference",
             {"model": "yolo", "version": "8.1", "latency_ms": 30,
              "confidence": rng.uniform(0.2, 0.5)})
    results = jobs.check_drift(db)
    assert results["rpi5-vision"] > 0.2
    assert len(open_alerts(db, "drift")) == 1


def test_in_distribution_does_not_trigger_drift(mqtt, db):
    rng = random.Random(3)
    for _ in range(500):  # misma distribución que la referencia de validación
        mqtt("edge/rpi5-vision/inference",
             {"model": "yolo", "version": "8.1", "latency_ms": 30,
              "confidence": rng.betavariate(8, 2)})
    assert jobs.check_drift(db)["rpi5-vision"] < 0.1
    assert open_alerts(db, "drift") == []


def test_drift_requires_minimum_samples(mqtt, db):
    mqtt("edge/rpi5-vision/inference",
         {"model": "yolo", "version": "8.1", "latency_ms": 30, "confidence": 0.1})
    assert jobs.check_drift(db) == {}
