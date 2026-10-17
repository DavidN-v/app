"""Raspberry Pi 5 · Agente de dispositivos (real en contenedor).

- Reporta su propia telemetría con el agente edge (CPU, RAM, disco reales del contenedor).
- Escucha la telemetría de toda la flota por MQTT y la clasifica en vivo con un detector
  de anomalías (z-score móvil): ese es su "modelo", y su latencia y confianza son reales.
- Pantalla local en :8103 con estado, tiempo activo y tráfico MQTT de los últimos 60 s.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt
from edge_agent import system
from edge_agent.agent import EdgeAgent
from edge_agent.deployer import ModelStore

from anomaly import AnomalyDetector

log = logging.getLogger("agent-device")

DEVICE_ID = os.getenv("EDGE_DEVICE_ID", "rpi5-agent")
MODEL_NAME, MODEL_VERSION = "telemetry-agent", os.getenv("AGENT_MODEL_VERSION", "1.4")
PORT = int(os.getenv("AGENT_PORT", "8103"))


class Traffic:
    """Mensajes MQTT enviados y recibidos por segundo (últimos 60 s)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sent: deque = deque([0] * 60, maxlen=60)
        self.received: deque = deque([0] * 60, maxlen=60)
        self.second = int(time.time())

    def _roll(self) -> None:
        now = int(time.time())
        while self.second < now:
            self.sent.append(0)
            self.received.append(0)
            self.second += 1

    def add(self, sent: int = 0, received: int = 0) -> None:
        with self.lock:
            self._roll()
            self.sent[-1] += sent
            self.received[-1] += received

    def snapshot(self) -> tuple[list[int], list[int]]:
        with self.lock:
            self._roll()
            return list(self.sent), list(self.received)


class Device:
    def __init__(self) -> None:
        self.started = time.time()
        self.traffic = Traffic()
        self.detector = AnomalyDetector()
        self.anomalies: deque = deque(maxlen=12)
        self.connected = False
        self.classified = 0
        self.last_latency_ms: float | None = None

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"device-{DEVICE_ID}")
        self.client.will_set(f"edge/{DEVICE_ID}/status", "offline", qos=1, retain=True)
        self.agent = EdgeAgent(DEVICE_ID, self, ModelStore(Path(os.getenv("EDGE_MODELS_DIR", "/data/models"))),
                               float(os.getenv("EDGE_INTERVAL_S", "2")))
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = lambda *a: setattr(self, "connected", False)
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(1, 30)

    # El agente publica a través de este método: así se cuentan los mensajes enviados
    def publish(self, topic, payload, qos=0, retain=False):
        self.traffic.add(sent=1)
        return self.client.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic, qos=0):
        return self.client.subscribe(topic, qos)

    def on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = True
        self.agent.on_connect(self, userdata, flags, reason_code, properties)
        client.subscribe("edge/+/telemetry", qos=0)

    def on_message(self, client, userdata, msg) -> None:
        self.traffic.add(received=1)
        parts = msg.topic.split("/")
        if len(parts) == 3 and parts[2] == "telemetry":
            if parts[1] != DEVICE_ID:
                self.classify(parts[1], msg.payload)
            return
        self.agent.on_message(client, userdata, msg)

    def classify(self, device: str, payload: bytes) -> None:
        try:
            reading = json.loads(payload)
        except ValueError:
            return
        with self.agent.track_inference(MODEL_NAME, MODEL_VERSION) as trace:
            verdict = self.detector.observe(device, reading)
            trace.confidence = verdict.normality
        self.classified += 1
        if verdict.anomalous:
            self.anomalies.appendleft({"device": device, "metric": verdict.worst_metric, "z": verdict.z,
                                       "value": reading.get(verdict.worst_metric), "ts": time.time()})

    def state(self) -> dict:
        sent, received = self.traffic.snapshot()
        sysinfo = system.collect()
        return {
            "device": DEVICE_ID, "connected": self.connected, "uptime_s": int(time.time() - self.started),
            "cpu": sysinfo["cpu"], "ram": sysinfo["ram"], "temp": sysinfo["temp"],
            "sent": sent, "received": received, "classified": self.classified,
            "anomalies": list(self.anomalies), "model": f"{MODEL_NAME} {MODEL_VERSION} · z-score móvil",
        }

    def start(self) -> None:
        self.client.connect_async(os.getenv("EDGE_MQTT_HOST", "localhost"), int(os.getenv("EDGE_MQTT_PORT", "1883")), 30)
        self.client.loop_start()
        threading.Thread(target=self.agent.run, daemon=True).start()


PAGE = (Path(__file__).parent / "screen.html").read_bytes()


def make_handler(device: Device):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                body, ctype = PAGE, "text/html; charset=utf-8"
            elif self.path == "/state":
                body, ctype = json.dumps(device.state()).encode(), "application/json"
            elif self.path == "/healthz":
                body, ctype = b"ok", "text/plain"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    device = Device()
    device.start()
    log.info("Pantalla local en http://0.0.0.0:%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(device)).serve_forever()


if __name__ == "__main__":
    main()
