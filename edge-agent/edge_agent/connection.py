"""Conexión MQTT de los dispositivos, configurada con variables de entorno.

Todos los dispositivos (el agente genérico y las aplicaciones de devices/) crean su cliente
con esta función, así la forma de conectarse es la misma en todos:

    EDGE_MQTT_HOST       dirección del servidor (por defecto localhost)
    EDGE_MQTT_PORT       puerto (1883 sin cifrar, 8883 con TLS)
    EDGE_MQTT_USERNAME   usuario y contraseña, si el broker los exige
    EDGE_MQTT_PASSWORD
    EDGE_MQTT_TLS=1      activa el cifrado TLS
    EDGE_MQTT_CA         certificado de la autoridad que firmó el del servidor
    EDGE_MQTT_CERT       certificado y clave propios del dispositivo, si el broker
    EDGE_MQTT_KEY        exige que cada dispositivo se identifique con certificado
"""

import os

import paho.mqtt.client as mqtt


def tls_enabled() -> bool:
    return os.getenv("EDGE_MQTT_TLS") == "1"


def create_client(device_id: str, client_id: str | None = None) -> mqtt.Client:
    """Crea el cliente MQTT del dispositivo con sus credenciales y su último mensaje.

    El último mensaje ("offline" retenido) lo publica el broker en nombre del dispositivo
    si este se desconecta sin avisar, por ejemplo por un corte de luz o de red.
    """
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
    """Conecta en segundo plano. Si el servidor no está disponible, se reintenta solo."""
    default_port = "8883" if tls_enabled() else "1883"
    client.connect_async(os.getenv("EDGE_MQTT_HOST", "localhost"),
                         int(os.getenv("EDGE_MQTT_PORT", default_port)), keepalive=30)
    client.loop_start()
