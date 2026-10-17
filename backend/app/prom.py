"""Métricas Prometheus expuestas en /metrics y recogidas por VictoriaMetrics."""

from prometheus_client import Counter, Gauge

DEVICE_CPU = Gauge("edge_device_cpu_percent", "Uso de CPU", ["device"])
DEVICE_RAM = Gauge("edge_device_ram_percent", "Uso de RAM", ["device"])
DEVICE_TEMP = Gauge("edge_device_temperature_celsius", "Temperatura", ["device"])
DEVICE_UP = Gauge("edge_device_up", "1 si el dispositivo está en línea", ["device"])
INFERENCE_LATENCY = Gauge("edge_inference_latency_ms", "Última latencia de inferencia", ["device", "model"])
INFERENCES = Counter("edge_inferences_total", "Inferencias reportadas", ["device", "model"])
MQTT_MESSAGES = Counter("edge_mqtt_messages_total", "Mensajes MQTT recibidos", ["kind"])
ALERTS_RAISED = Counter("edge_alerts_raised_total", "Alertas generadas", ["kind", "severity"])
DRIFT_PSI = Gauge("edge_model_drift_psi", "PSI de la distribución de confianza", ["device", "model"])
