import time
from datetime import timedelta

from sqlalchemy import create_engine, text

from app import jobs, migrate
from app.hub import hub
from app.models import Alert, Deployment, LatencyMinute, utcnow
from tests.test_deployments import approved_model, bring_online


def pending_deployment(client, auth, mqtt):
    model = approved_model(client, auth)
    bring_online(mqtt)
    r = client.post("/api/deployments", headers=auth("operator"),
                    json={"model_id": model["id"], "device_id": "rpi5-vision"})
    assert r.status_code == 202
    return r.json()



def test_deployment_starts_as_requested(client, auth, mqtt):
    assert pending_deployment(client, auth, mqtt)["stage"] == "requested"


def test_progress_advances_stage(client, auth, mqtt, db):
    dep = pending_deployment(client, auth, mqtt)
    for stage in ("downloading", "verifying", "installing"):
        mqtt("edge/rpi5-vision/deploy/progress", {"deployment_id": dep["id"], "stage": stage})
        assert db.get(Deployment, dep["id"]).stage == stage


def test_progress_never_goes_backwards(client, auth, mqtt, db):
    dep = pending_deployment(client, auth, mqtt)
    mqtt("edge/rpi5-vision/deploy/progress", {"deployment_id": dep["id"], "stage": "installing"})
    mqtt("edge/rpi5-vision/deploy/progress", {"deployment_id": dep["id"], "stage": "downloading"})
    assert db.get(Deployment, dep["id"]).stage == "installing"


def test_unknown_stage_is_ignored(client, auth, mqtt, db):
    dep = pending_deployment(client, auth, mqtt)
    mqtt("edge/rpi5-vision/deploy/progress", {"deployment_id": dep["id"], "stage": "hacking"})
    assert db.get(Deployment, dep["id"]).stage == "requested"


def test_ack_sets_final_stage(client, auth, mqtt, db):
    dep = pending_deployment(client, auth, mqtt)
    mqtt("edge/rpi5-vision/deploy/ack", {"deployment_id": dep["id"], "status": "succeeded"})
    assert db.get(Deployment, dep["id"]).stage == "confirmed"


def test_stuck_deployment_times_out(client, auth, mqtt, db):
    dep = pending_deployment(client, auth, mqtt)
    mqtt("edge/rpi5-vision/deploy/progress", {"deployment_id": dep["id"], "stage": "verifying"})
    row = db.get(Deployment, dep["id"])
    row.created_at = utcnow() - timedelta(minutes=10)
    db.commit()
    assert jobs.check_deploy_timeouts(db) == [dep["id"]]
    db.expire_all()
    row = db.get(Deployment, dep["id"])
    assert (row.status, row.stage) == ("failed", "failed")
    assert "verifying" in row.message
    assert db.query(Alert).filter_by(kind="deployment_failed").count() == 1


def test_fresh_deployment_does_not_time_out(client, auth, mqtt, db):
    pending_deployment(client, auth, mqtt)
    assert jobs.check_deploy_timeouts(db) == []



def test_high_ram_alert_uses_policy(client, auth, mqtt, db):
    mqtt("edge/rpi5-genai/telemetry", {"cpu": 10, "ram": 91, "temp": 50})
    assert db.query(Alert).filter_by(kind="high_ram").count() == 1



def test_latency_5m_returns_recent_points(client, auth, mqtt):
    mqtt("edge/uno-q/inference", {"model": "yolo-nano", "version": "8.1", "latency_ms": 24})
    r = client.get("/api/metrics/latency?window=5m", headers=auth("viewer")).json()
    assert r["window"] == "5m"
    assert r["series"]["uno-q"][-1][1] == 24


def test_latency_history_survives_in_db(client, auth, db):
    hub._buckets.clear()
    base = (int(time.time()) // 60) * 60 - 600  # hace 10 minutos
    hub.record_latency("ventuno", 30, ts=base + 5)
    hub.record_latency("ventuno", 50, ts=base + 20)
    hub.record_latency("ventuno", 90, ts=base + 70)
    assert jobs.flush_latency(db) == 2
    rows = db.query(LatencyMinute).filter_by(device_id="ventuno").order_by(LatencyMinute.minute).all()
    assert [(r.avg, r.max, r.count) for r in rows] == [(40.0, 50.0, 2), (90.0, 90.0, 1)]

    hub.latency.clear()  # simula que la API se reinició: el historial sale de la base de datos
    series = client.get("/api/metrics/latency?window=1h", headers=auth("viewer")).json()["series"]
    assert [p[1] for p in series["ventuno"]] == [40.0, 90.0]


def test_latency_rejects_unknown_window(client, auth):
    assert client.get("/api/metrics/latency?window=7d", headers=auth("viewer")).status_code == 422



def test_migration_adds_missing_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE deployments (id INTEGER PRIMARY KEY, status VARCHAR(16))"))
    assert migrate.ensure_columns(engine) == ["deployments.stage"]
    assert migrate.ensure_columns(engine) == []



def test_access_log_redacts_ws_token():
    import logging

    from app.main import RedactTokens

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '%s - "%s %s"', ("127.0.0.1", "WebSocket", "/ws?token=eyJabc.def.ghi"), None)
    RedactTokens().filter(record)
    assert "eyJabc" not in record.getMessage()
    assert "token=***" in record.getMessage()
