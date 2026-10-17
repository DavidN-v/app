# Edge Governance

Plataforma de **gobernanza y observabilidad de modelos de IA en dispositivos edge**
(Raspberry Pi 5, Arduino Uno Q / Ventuno, ESP32).

- **Observabilidad en tiempo real**: CPU, RAM, temperatura, latencia de inferencia y drift por dispositivo.
- **Registro de modelos** con ciclo de vida `borrador → aprobado → desplegado → retirado`.
- **Motor de políticas**: bloquea despliegues sin firma, con licencias no permitidas, en hardware
  incompatible o en dispositivos desconectados.
- **Despliegue OTA seguro**: verificación SHA-256, instalación atómica y rollback en el dispositivo.
- **Auditoría inmutable**: cada acción queda en un registro encadenado por hash, verificable desde la UI.
- **Alertas** deduplicadas por temperatura, CPU, latencia, drift (PSI), desconexión y fallos de despliegue.
- **RBAC** con separación de funciones: quien registra un modelo no puede aprobarlo.

## Arquitectura

```
 Dispositivos edge                          Nodo de gobernanza (Raspberry Pi 5 / servidor)
┌──────────────────────┐                  ┌─────────────────────────────────────────────┐
│ RPi 5  edge-agent    │──┐               │  Mosquitto (MQTT)                           │
│ Arduino / ESP32 fw   │──┼── MQTT ──────►│     │                                       │
│ (o el simulador)     │──┘  edge/{id}/*  │  FastAPI ── PostgreSQL (registro, auditoría)│
└──────────────────────┘                  │     │  ├── /metrics ─► VictoriaMetrics ─► Grafana
          ▲                               │     │  └── WebSocket /ws                    │
          └──── edge/{id}/deploy ─────────│     ▼                                       │
                                          │  Angular (nginx) :8080                      │
                                          └─────────────────────────────────────────────┘
```

| Componente | Tecnología |
|---|---|
| API | Python 3.12 · FastAPI · SQLAlchemy 2 · Pydantic 2 · paho-mqtt · prometheus-client |
| Frontend | Angular 22 (standalone, signals, zoneless) · ECharts · SCSS |
| Agente edge | Python · paho-mqtt · psutil |
| Firmware | C++ · Arduino/ESP-IDF · PubSubClient · ArduinoJson · TFLite Micro |
| Infraestructura | Docker Compose · Mosquitto · PostgreSQL 16 · VictoriaMetrics · Grafana |
| Pruebas | pytest · Vitest · ruff · GitHub Actions |

## Arranque rápido (Docker)

```bash
cp .env.example .env            # cambia los secretos
docker compose --profile demo up -d --build
```

| Servicio | URL |
|---|---|
| Consola Angular | http://localhost:8080 |
| API + Swagger | http://localhost:8000/docs |
| Grafana | http://localhost:3000 (admin / admin) |
| VictoriaMetrics | http://localhost:8428 |

El perfil `demo` arranca el **simulador**, que reproduce los 6 dispositivos del laboratorio
e inyecta incidentes periódicos (temperatura alta en la GenAI, latencia en el Ventuno,
drift en la cámara de visión). Sin `--profile demo` la plataforma espera a dispositivos reales.

Usuarios de demostración (contraseña `<usuario>123`):

| Usuario | Rol | Puede |
|---|---|---|
| `viewer` | viewer | ver todo salvo auditoría |
| `operator` | operator | registrar modelos, desplegar, gestionar alertas |
| `approver` | approver | aprobar/retirar modelos, ver y verificar auditoría |
| `admin` | admin | todo + políticas y alta/baja de dispositivos |

## Desarrollo local (sin Docker)

```bash
# 1. Broker MQTT (cualquiera: mosquitto, o `pip install amqtt && amqtt`)
# 2. API
cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux/mac: .venv/bin/
.venv/Scripts/uvicorn app.main:app --reload            # SQLite por defecto
# 3. Simulador
python simulator/simulate.py
# 4. Frontend (proxy a :8000 ya configurado)
cd frontend && npm install && npm start                # http://localhost:4200
```

## Pruebas

```bash
cd backend    && pytest && ruff check app tests        # API: auth, RBAC, ciclo de vida, políticas,
                                                       # despliegues, ingesta MQTT, alertas, drift, auditoría
cd edge-agent && pytest                                # OTA: hash, atomicidad, rollback, acks
cd frontend   && npx ng test --watch=false             # servicios, interceptor, tiempo real, componentes
```

## Conectar un dispositivo real

**Raspberry Pi 5**

```bash
pip install ./edge-agent
EDGE_DEVICE_ID=rpi5-vision EDGE_MQTT_HOST=<ip-del-nodo> edge-agent
```

Instrumenta tu inferencia para que reporte latencia y confianza (alimenta el drift):

```python
with agent.track_inference("yolo", "8.1") as t:
    outputs = session.run(None, {"images": frame})
    t.confidence = float(best_score)
```

**ESP32**: `firmware/esp32` (PlatformIO). Genera `src/model_data.h` con
`xxd -i env_regressor.tflite` y define `WIFI_SSID`, `WIFI_PASS`, `MQTT_HOST` antes de compilar.

El dispositivo debe darse de alta antes (`POST /api/devices`, rol admin): los mensajes de
dispositivos no registrados generan una alerta y se descartan.

## Contrato MQTT

| Tópico | Dirección | Payload |
|---|---|---|
| `edge/{id}/telemetry` | dispositivo → API | `{"cpu": 18.2, "ram": 42, "temp": 51.3}` |
| `edge/{id}/inference` | dispositivo → API | `{"model": "yolo", "version": "8.1", "latency_ms": 28, "confidence": 0.92}` |
| `edge/{id}/status` | dispositivo → API | `online` / `offline` (LWT, retenido) |
| `edge/{id}/deploy` | API → dispositivo | `{"deployment_id", "model", "version", "url", "sha256", "signature"}` |
| `edge/{id}/deploy/ack` | dispositivo → API | `{"deployment_id", "status": "succeeded"\|"failed", "message"}` |

## Producción: lista de comprobación

- [ ] Cambiar todos los secretos de `.env` (`EG_JWT_SECRET` de al menos 32 caracteres aleatorios).
- [ ] Mosquitto con `infra/mosquitto/mosquitto.prod.conf`: mTLS, un certificado por dispositivo
      y la ACL `infra/mosquitto/acl` (cada dispositivo solo publica en su propio árbol).
- [ ] TLS en nginx (o un proxy delante) para la consola y la API.
- [ ] Firmar los artefactos con `cosign` y verificar la firma en el agente antes de instalar.
- [ ] `EG_SEED_DEMO_DATA=false` y usuarios reales.
- [ ] Copias de seguridad del volumen `postgres-data`; migraciones con Alembic si el esquema evoluciona.
