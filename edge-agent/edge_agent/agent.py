"""Agente edge: publica telemetría e inferencias y ejecuta despliegues OTA.

Uso en un dispositivo:
    EDGE_DEVICE_ID=rpi5-vision EDGE_MQTT_HOST=192.168.1.10 python -m edge_agent.agent

Para medir inferencias desde tu propio código:
    with agent.track_inference("yolo", "8.1") as t:
        boxes = session.run(...)
        t.confidence = float(boxes[0].score)
"""

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt

from . import system
from .deployer import ModelStore

log = logging.getLogger("edge_agent")


@dataclass
class InferenceTrace:
    confidence: float | None = None


class EdgeAgent:
    def __init__(self, device_id: str, client, store: ModelStore, interval_s: float = 5.0) -> None:
        self.device_id = device_id
        self.client = client
        self.store = store
        self.interval_s = interval_s
        self._stop = threading.Event()

    def topic(self, suffix: str) -> str:
        return f"edge/{self.device_id}/{suffix}"

    # --- publicación ---------------------------------------------------------
    def publish(self, suffix: str, payload, qos: int = 0, retain: bool = False) -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.client.publish(self.topic(suffix), body, qos=qos, retain=retain)

    def publish_telemetry(self) -> dict:
        data = system.collect()
        self.publish("telemetry", data)
        return data

    @contextmanager
    def track_inference(self, model: str, version: str):
        trace = InferenceTrace()
        start = time.perf_counter()
        yield trace
        latency = (time.perf_counter() - start) * 1000
        self.publish("inference", {"model": model, "version": version,
                                   "latency_ms": round(latency, 2),
                                   "confidence": trace.confidence})

    # --- despliegues ---------------------------------------------------------
    def handle_deploy(self, raw: bytes) -> dict:
        try:
            command = json.loads(raw)
            deployment_id = command["deployment_id"]
        except (ValueError, KeyError) as exc:
            log.error("Orden de despliegue inválida: %s", exc)
            return {}
        def progress(stage: str) -> None:
            self.publish("deploy/progress", {"deployment_id": deployment_id, "stage": stage}, qos=1)

        result = self.store.install(command, progress=progress)
        ack = {"deployment_id": deployment_id,
               "status": "succeeded" if result.ok else "failed",
               "message": result.message}
        self.publish("deploy/ack", ack, qos=1)
        log.info("Despliegue %s: %s", deployment_id, result.message)
        return ack

    def on_message(self, client, userdata, msg) -> None:
        if msg.topic == self.topic("deploy"):
            # Descargar puede tardar: no bloquear el hilo de red de MQTT
            threading.Thread(target=self.handle_deploy, args=(msg.payload,), daemon=True).start()

    def on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        log.info("Conectado al broker (%s)", reason_code)
        client.subscribe(self.topic("deploy"), qos=1)
        self.publish("status", "online", qos=1, retain=True)

    # --- ciclo de vida -------------------------------------------------------
    def run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.publish_telemetry()
            except Exception:
                log.exception("Error recogiendo telemetría")

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    device_id = os.environ["EDGE_DEVICE_ID"]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"agent-{device_id}")
    if user := os.getenv("EDGE_MQTT_USERNAME"):
        client.username_pw_set(user, os.getenv("EDGE_MQTT_PASSWORD"))
    if os.getenv("EDGE_MQTT_TLS") == "1":
        client.tls_set(ca_certs=os.getenv("EDGE_MQTT_CA"), certfile=os.getenv("EDGE_MQTT_CERT"),
                       keyfile=os.getenv("EDGE_MQTT_KEY"))
    # Last Will: si el agente muere, el broker anuncia "offline" por nosotros
    client.will_set(f"edge/{device_id}/status", "offline", qos=1, retain=True)

    agent = EdgeAgent(device_id, client,
                      ModelStore(Path(os.getenv("EDGE_MODELS_DIR", "./models"))),
                      float(os.getenv("EDGE_INTERVAL_S", "5")))
    client.on_connect = agent.on_connect
    client.on_message = agent.on_message
    client.reconnect_delay_set(1, 30)
    client.connect_async(os.getenv("EDGE_MQTT_HOST", "localhost"),
                         int(os.getenv("EDGE_MQTT_PORT", "1883")), keepalive=30)
    client.loop_start()
    try:
        agent.run()
    except KeyboardInterrupt:
        pass
    finally:
        agent.publish("status", "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
