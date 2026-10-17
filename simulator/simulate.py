"""Simulador de los 6 dispositivos del laboratorio.

Permite ver la plataforma funcionando sin hardware. Cada dispositivo publica
telemetría e inferencias con perfiles realistas, inyecta incidentes de vez en
cuando (temperatura, latencia, drift) y responde a las órdenes de despliegue.

    python simulate.py --host localhost
"""

import argparse
import json
import math
import random
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt


@dataclass
class Profile:
    device_id: str
    model: str
    version: str
    cpu: float
    ram: float
    temp: float
    latency: float
    jitter: float
    has_confidence: bool = False
    incident: str | None = None  # tipo de incidente que puede sufrir
    state: dict = field(default_factory=dict)


PROFILES = [
    Profile("rpi5-vision", "yolo", "8.1", 42, 68, 55, 28, 4, True, "drift"),
    Profile("rpi5-genai", "llama3-mini", "3.2-q4", 34, 68, 62, 42, 6, None, "high_temperature"),
    Profile("rpi5-agent", "telemetry-agent", "1.4", 12, 28, 43, 31, 3, True),
    Profile("uno-q", "yolo-nano", "8.1-int8", 8, 18, 39, 25, 3, True),
    Profile("ventuno", "anomaly-ts", "2.0", 6, 16, 41, 37, 5, None, "high_latency"),
    Profile("esp32-env", "env-regressor", "1.1", 10, 22, 36, 29, 2, None),
]


class Simulator:
    def __init__(self, host: str, port: int, rate: float, incidents: bool) -> None:
        self.host, self.port, self.rate, self.incidents = host, port, rate, incidents
        self.clients: dict[str, mqtt.Client] = {}
        self.t0 = time.time()

    def connect(self, p: Profile) -> mqtt.Client:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{p.device_id}")
        c.will_set(f"edge/{p.device_id}/status", "offline", qos=1, retain=True)

        def on_connect(client, *_):
            client.subscribe(f"edge/{p.device_id}/deploy", qos=1)
            client.publish(f"edge/{p.device_id}/status", "online", qos=1, retain=True)

        def on_message(client, _userdata, msg):
            threading.Thread(target=self.deploy, args=(client, p, msg.payload), daemon=True).start()

        c.on_connect, c.on_message = on_connect, on_message
        c.reconnect_delay_set(1, 10)
        c.connect_async(self.host, self.port, keepalive=20)
        c.loop_start()
        return c

    def deploy(self, client: mqtt.Client, p: Profile, raw: bytes) -> None:
        cmd = json.loads(raw)
        topic = f"edge/{p.device_id}/deploy/progress"
        ok = random.random() > 0.1
        for stage, secs in (("downloading", (2, 4)), ("verifying", (1, 2)), ("installing", (1, 2))):
            client.publish(topic, json.dumps({"deployment_id": cmd["deployment_id"], "stage": stage}), qos=1)
            time.sleep(random.uniform(*secs))
            if stage == "verifying" and not ok:
                break  # el hash no coincide: no se llega a instalar
        if ok:
            p.model, p.version = cmd["model"], cmd["version"]
        ack = {"deployment_id": cmd["deployment_id"], "status": "succeeded" if ok else "failed",
               "message": f"{cmd['model']} v{cmd['version']} instalado" if ok
               else "sha256 no coincide tras la descarga"}
        client.publish(f"edge/{p.device_id}/deploy/ack", json.dumps(ack), qos=1)

    def incident_active(self, p: Profile) -> bool:
        if not self.incidents or not p.incident:
            return False
        # Cada dispositivo con incidente lo sufre durante 40 s de cada ~4 min, desfasados
        phase = (time.time() - self.t0 + hash(p.device_id) % 120) % 240
        return phase > 200

    def tick(self, p: Profile, t: float) -> None:
        c = self.clients[p.device_id]
        wave = math.sin(t / 15 + hash(p.device_id) % 10)
        incident = self.incident_active(p)

        temp = p.temp + 3 * wave + random.gauss(0, 0.4)
        latency = max(1.0, p.latency + p.jitter * wave + random.gauss(0, p.jitter / 2))
        if incident and p.incident == "high_temperature":
            temp += 25
        if incident and p.incident == "high_latency":
            latency *= 4

        telemetry = {
            "cpu": round(max(0, min(100, p.cpu + 8 * wave + random.gauss(0, 2))), 1),
            "ram": round(max(0, min(100, p.ram + random.gauss(0, 0.8))), 1),
            "temp": round(temp, 1),
        }
        c.publish(f"edge/{p.device_id}/telemetry", json.dumps(telemetry))

        inference = {"model": p.model, "version": p.version, "latency_ms": round(latency, 1)}
        if p.has_confidence:
            # Normal: Beta(8,2), igual que la referencia de validación del modelo.
            # Incidente de drift (p. ej. la cámara se ensucia): la confianza cae a Beta(3,4).
            a, b = (3, 4) if incident and p.incident == "drift" else (8, 2)
            inference["confidence"] = round(random.betavariate(a, b), 3)
        c.publish(f"edge/{p.device_id}/inference", json.dumps(inference))

    def run(self) -> None:
        for p in PROFILES:
            self.clients[p.device_id] = self.connect(p)
        print(f"Simulando {len(PROFILES)} dispositivos contra {self.host}:{self.port}")
        try:
            while True:
                t = time.time() - self.t0
                for p in PROFILES:
                    self.tick(p, t)
                time.sleep(1 / self.rate)
        except KeyboardInterrupt:
            pass
        finally:
            for device_id, c in self.clients.items():
                c.publish(f"edge/{device_id}/status", "offline", qos=1, retain=True)
                c.loop_stop()
                c.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--rate", type=float, default=1.0, help="mensajes por segundo por dispositivo")
    ap.add_argument("--no-incidents", action="store_true")
    args = ap.parse_args()
    Simulator(args.host, args.port, args.rate, not args.no_incidents).run()
