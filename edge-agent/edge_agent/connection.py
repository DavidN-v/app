"""Conexión MQTT de los dispositivos, configurada con variables de entorno."""

import os

import paho.mqtt.client as mqtt


def tls_enabled() -> bool:
    return os.getenv("EDGE_MQTT_TLS") == "1"


def create_client(device_id: str, client_id: str | None = None) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or f"device-{device_id}")
    if user := os.getenv("EDGE_MQTT_USERNAME"):
        client.username_pw_set(user, os.getenv("EDGE_MQTT_PASSWORD"))
    if tls_enabled():
        client.tls_set(ca_certs=os.getenv("EDGE_MQTT_CA"), certfile=os.getenv("EDGE_MQTT_CERT"),
                       keyfile=os.getenv("EDGE_MQTT_KEY"))
    client.will_set(f"edge/{device_id}/status", "offline", qos=1, retain=True)
    client.reconnect_delay_set(1, 30)
    return client


def connect(client: mqtt.Client) -> None:
    default_port = "8883" if tls_enabled() else "1883"
    client.connect_async(os.getenv("EDGE_MQTT_HOST", "localhost"),
                         int(os.getenv("EDGE_MQTT_PORT", default_port)), keepalive=30)
    client.loop_start()
