"""Conexión entre la API y el broker MQTT.

MQTT es un protocolo de mensajería ligero muy usado en dispositivos IoT: los dispositivos
publican mensajes en temas (topics) y los interesados se suscriben a ellos. La API se suscribe
a todos los temas edge/# para recibir la telemetría y publica las órdenes de despliegue.
"""

import json
import logging

import paho.mqtt.client as mqtt

from . import ingest
from .config import get_settings
from .db import SessionLocal

log = logging.getLogger(__name__)


class MqttBridge:
    """Cliente MQTT de la API: recibe los mensajes de los dispositivos y envía despliegues.

    La librería paho atiende la red en un hilo propio y se reconecta sola si el broker se cae.
    """

    def __init__(self) -> None:
        s = get_settings()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="governance-api")
        if s.mqtt_username:
            self.client.username_pw_set(s.mqtt_username, s.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._host, self._port = s.mqtt_host, s.mqtt_port

    def start(self) -> None:
        self.client.connect_async(self._host, self._port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_deploy(self, device_id: str, command: dict) -> None:
        """Envía la orden de despliegue. QoS 1 garantiza que el broker la entregue al menos una vez."""
        self.client.publish(f"edge/{device_id}/deploy", json.dumps(command), qos=1)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        # Se suscribe en cada conexión para recuperar la suscripción tras una reconexión
        log.info("MQTT conectado (%s)", reason_code)
        client.subscribe("edge/#", qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        """Procesa cada mensaje con su propia sesión de base de datos."""
        if msg.topic.endswith("/deploy"):
            return  # órdenes publicadas por nosotros mismos
        with SessionLocal() as db:
            try:
                ingest.handle(db, msg.topic, msg.payload, retained=bool(msg.retain))
            except Exception:
                log.exception("Error procesando %s", msg.topic)


class NullBridge:
    """Sustituto sin red que se usa en las pruebas o cuando MQTT está desactivado.
    Guarda las órdenes publicadas para que las pruebas puedan comprobarlas."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def publish_deploy(self, device_id: str, command: dict) -> None:
        self.published.append((device_id, command))
