# Edge Governance

Plataforma de gobernanza y observabilidad de modelos de inteligencia artificial que se ejecutan
en dispositivos edge (Raspberry Pi 5, Arduino Uno Q, Arduino Ventuno y ESP32).

## 1. Objetivo

Cuando un modelo de IA se instala en muchos dispositivos pequeños, repartidos y sin supervisión
directa, aparecen dos problemas:

1. **Observabilidad:** saber en todo momento si cada dispositivo funciona, cuánto tarda el modelo
   en responder y si sus resultados siguen siendo fiables.
2. **Gobernanza:** controlar qué modelo se instala en cada dispositivo, quién lo aprueba y dejar
   constancia de todas las decisiones.

Este proyecto resuelve ambos problemas con una consola web central que recibe los datos de los
dispositivos en tiempo real y aplica unas políticas antes de permitir cualquier cambio.

## 2. Funcionalidades

- **Monitorización en tiempo real** de CPU, RAM, temperatura y latencia de inferencia de cada dispositivo.
- **Detección de drift:** se compara la distribución de las confianzas del modelo en producción
  con la medida durante su validación, mediante el índice de estabilidad poblacional (PSI).
- **Registro de modelos** con ciclo de vida: borrador → aprobado → desplegado → retirado.
- **Políticas configurables:** se bloquean los despliegues de modelos sin firma, con licencias no
  permitidas, incompatibles con el hardware o dirigidos a dispositivos desconectados.
- **Despliegue a distancia seguro:** el dispositivo verifica el resumen SHA-256 del modelo antes de
  instalarlo y conserva la versión anterior por si hay que volver atrás.
- **Alertas** por temperatura, CPU, RAM, latencia, drift, desconexión, fallos de despliegue y
  modelos que no coinciden con el registro. Se cierran solas cuando la condición desaparece.
- **Auditoría encadenada:** cada acción se guarda junto con el resumen de la anterior, de modo que
  cualquier alteración del historial se detecta.
- **Control de acceso por roles,** con separación de funciones: quien registra un modelo no puede aprobarlo.

## 3. Arquitectura

```
 Dispositivos edge                          Nodo de gobernanza
┌──────────────────────┐                  ┌─────────────────────────────────────────────┐
│ Raspberry Pi 5       │──┐               │  Mosquitto (broker MQTT)                    │
│ Arduino / ESP32      │──┼── MQTT ──────►│     │                                       │
│ (o el simulador)     │──┘  edge/{id}/*  │  API FastAPI ── PostgreSQL                  │
└──────────────────────┘                  │     │  ├── /metrics ─► VictoriaMetrics ─► Grafana
          ▲                               │     │  └── WebSocket /ws                    │
          └──── edge/{id}/deploy ─────────│     ▼                                       │
                                          │  Consola Angular (nginx) :8080              │
                                          └─────────────────────────────────────────────┘
```

Los dispositivos publican sus datos en el broker MQTT. La API los recibe, actualiza la base de
datos, evalúa las políticas y reenvía cada evento a la consola a través de un WebSocket. Las
órdenes de despliegue siguen el camino inverso.

| Componente | Tecnologías |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, paho-mqtt, prometheus-client |
| Consola web | Angular 22, ECharts, SCSS |
| Agente de los dispositivos | Python, paho-mqtt, psutil |
| Firmware ESP32 | C++, Arduino, PubSubClient, ArduinoJson, TensorFlow Lite Micro |
| Infraestructura | Docker Compose, Mosquitto, PostgreSQL 16, VictoriaMetrics, Grafana |
| Pruebas | pytest, Vitest, ruff, GitHub Actions |

### Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `backend/` | API: modelo de datos, ingesta MQTT, políticas, alertas, drift y auditoría |
| `frontend/` | Consola web |
| `edge-agent/` | Agente que se instala en cada dispositivo: telemetría e instalación de modelos |
| `devices/` | Raspberry Pi 5 emuladas en contenedores que ejecutan modelos reales |
| `simulator/` | Simulador de los seis dispositivos, para probar la plataforma sin hardware |
| `firmware/esp32/` | Firmware del ESP32 y script de entrenamiento de su modelo |
| `infra/` | Configuración de Mosquitto, VictoriaMetrics y Grafana |

## 4. Puesta en marcha con Docker

```bash
cp .env.example .env            # cambiar las contraseñas y secretos
docker compose --profile demo up -d --build
```

| Servicio | Dirección |
|---|---|
| Consola | http://localhost:8080 |
| API y documentación | http://localhost:8000/docs |
| Grafana | http://localhost:3000 (admin / admin) |
| VictoriaMetrics | http://localhost:8428 |

El perfil `demo` arranca el simulador, que reproduce los seis dispositivos del laboratorio y
provoca incidentes periódicos (temperatura alta, latencia elevada y drift) para comprobar que la
plataforma los detecta. Sin ese perfil, la plataforma espera a dispositivos reales.

Usuarios iniciales (la contraseña es el nombre de usuario seguido de `123`):

| Usuario | Puede |
|---|---|
| `viewer` | consultar todo salvo la auditoría |
| `operator` | registrar modelos, solicitar despliegues y atender alertas |
| `approver` | además, aprobar y retirar modelos y consultar la auditoría |
| `admin` | además, cambiar políticas y dar de alta o de baja dispositivos |

## 5. Dispositivos con modelos reales

La carpeta `devices/` contiene tres Raspberry Pi 5 emuladas en contenedores. Ejecutan software
real; solo el hardware está sustituido. Cada contenedor está limitado a 4 núcleos, como una
Raspberry Pi 5, y mide su consumo respecto a una placa de 4 núcleos y 4 GB de RAM.

| Dispositivo | Qué ejecuta | Pantalla propia |
|---|---|---|
| `rpi5-vision` | Detector de objetos YOLOv8n con ONNX Runtime sobre fotografías del conjunto COCO | http://localhost:8101 |
| `rpi5-genai` | Modelo de lenguaje Qwen2.5-0.5B con llama.cpp, que responde preguntas sobre el estado de la flota | http://localhost:8102 |
| `rpi5-agent` | Detector de anomalías (puntuación z) sobre la telemetría de todos los dispositivos | http://localhost:8103 |

```bash
SIM_SKIP=rpi5-vision,rpi5-genai,rpi5-agent docker compose --profile demo --profile real up -d --build
```

`SIM_SKIP` indica al simulador qué dispositivos no debe imitar porque ya funcionan de verdad.

En `rpi5-vision`, cada 5 minutos la "lente se ensucia" durante un minuto (imagen desenfocada y
oscura): la confianza del modelo baja de verdad y la plataforma lo detecta como drift. La
distribución de referencia se midió con el propio modelo mediante `devices/vision/calibrate.py`.

### ESP32 en el simulador Wokwi

El firmware de `firmware/esp32` ejecuta una pequeña red neuronal que calcula un índice de confort
(0 a 100) a partir de la temperatura, la humedad y el CO₂, y muestra el resultado en una pantalla OLED.
El modelo se entrena con `firmware/esp32/model/train.py`, que también genera `src/model_data.h`.

1. Instalar la extensión Wokwi Simulator en VS Code y activar su licencia gratuita.
2. Compilar con PlatformIO: `pio run -e wokwi`.
3. Arrancar la plataforma añadiendo `esp32-env` a `SIM_SKIP`.
4. Abrir la carpeta `firmware/esp32` en VS Code y ejecutar **Wokwi: Start Simulator**.

## 6. Desarrollo sin Docker

```bash
# 1. Un broker MQTT en el puerto 1883 (por ejemplo, Mosquitto)
# 2. API (usa SQLite por defecto)
cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn app.main:app --reload
# 3. Simulador
python simulator/simulate.py
# 4. Consola (redirige las peticiones a la API en el puerto 8000)
cd frontend && npm install && npm start      # http://localhost:4200
```

En Linux y macOS, la carpeta de ejecutables del entorno virtual es `.venv/bin/`.

## 7. Pruebas

```bash
cd backend    && pytest && ruff check app tests
cd edge-agent && pytest
cd frontend   && npx ng test --watch=false
pytest devices/vision/tests devices/genai/tests devices/agent/tests
```

Las pruebas cubren la autenticación y los roles, el ciclo de vida de los modelos, las políticas,
los despliegues, la ingesta de mensajes, las alertas, el cálculo del drift, la auditoría, la
instalación de modelos en el dispositivo y los componentes de la consola.

## 8. Conectar un dispositivo físico

**Raspberry Pi 5**

```bash
pip install ./edge-agent
EDGE_DEVICE_ID=rpi5-vision EDGE_MQTT_HOST=<ip-del-servidor> edge-agent
```

Para que la plataforma reciba la latencia y la confianza de cada inferencia:

```python
with agent.track_inference("yolo", "8.1") as t:
    outputs = session.run(None, {"images": frame})
    t.confidence = float(best_score)
```

**ESP32:** compilar `firmware/esp32` con PlatformIO definiendo antes las variables de entorno
`WIFI_SSID`, `WIFI_PASS` y `MQTT_HOST`.

Todo dispositivo debe darse de alta antes en la plataforma (rol administrador). Los mensajes de
dispositivos no registrados se descartan y generan una alerta.

## 9. Mensajes MQTT

| Tema | Sentido | Contenido |
|---|---|---|
| `edge/{id}/telemetry` | dispositivo → API | `{"cpu": 18.2, "ram": 42, "temp": 51.3}` |
| `edge/{id}/inference` | dispositivo → API | `{"model": "yolo", "version": "8.1", "latency_ms": 28, "confidence": 0.92}` |
| `edge/{id}/status` | dispositivo → API | `online` / `offline` |
| `edge/{id}/deploy` | API → dispositivo | `{"deployment_id", "model", "version", "url", "sha256", "signature"}` |
| `edge/{id}/deploy/progress` | dispositivo → API | `{"deployment_id", "stage"}` |
| `edge/{id}/deploy/ack` | dispositivo → API | `{"deployment_id", "status": "succeeded" \| "failed", "message"}` |

## 10. Antes de un despliegue en producción

- Cambiar todos los secretos de `.env` (`EG_JWT_SECRET` con al menos 32 caracteres aleatorios).
- Configurar Mosquitto con `infra/mosquitto/mosquitto.prod.conf`: un certificado por dispositivo y
  la lista de permisos `infra/mosquitto/acl`, para que cada dispositivo solo publique en sus temas.
- Servir la consola y la API con HTTPS.
- Firmar los modelos y verificar la firma en el agente antes de instalarlos.
- Desactivar los datos de demostración (`EG_SEED_DEMO_DATA=false`) y crear usuarios reales.
- Hacer copias de seguridad del volumen `postgres-data`.
