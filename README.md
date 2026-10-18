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

En `rpi5-vision`, cada 10 minutos la "lente se ensucia" durante un minuto (imagen desenfocada y
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

## 8. Conectar dispositivos físicos

La plataforma no distingue entre un dispositivo emulado y uno físico: los dos se comunican con los
mismos mensajes MQTT. Para conectar hardware real hay que preparar el servidor, dar de alta el
dispositivo en la consola y arrancar en él su programa.

### 8.1 Preparar el servidor

El servidor es el ordenador donde corre la plataforma. Necesita una IP fija dentro de la red local
(en los ejemplos, `192.168.1.50`) y tener abiertos estos puertos de entrada:

| Puerto | Uso |
|---|---|
| 1883 | MQTT sin cifrar (opción A) |
| 8883 | MQTT cifrado con TLS (opción B) |
| 8080 | Consola web |
| 8000 | API; solo la necesita el asistente `rpi5-genai` |

En Windows, desde PowerShell como administrador:

```powershell
New-NetFirewallRule -DisplayName "Edge Governance" -Direction Inbound -Protocol TCP -LocalPort 1883,8883,8000,8080 -Action Allow
```

**Opción A: red de confianza, sin cifrar.** Adecuada para un laboratorio o para hacer pruebas. Se
arranca la plataforma sin los perfiles `demo` ni `real`, para que el simulador no suplante a los
dispositivos físicos:

```bash
docker compose up -d --build
```

Si se quiere mezclar dispositivos físicos con otros simulados, se añade `--profile demo` y se
indican en `SIM_SKIP` los identificadores de los físicos, por ejemplo `SIM_SKIP=rpi5-vision,esp32-env`.

**Opción B: producción, con TLS.** El broker solo acepta conexiones cifradas y cada dispositivo
se identifica con su propio certificado; así ningún dispositivo puede hacerse pasar por otro.

```bash
# 1. Certificados: IP del servidor y los identificadores de los dispositivos
infra/mosquitto/generar-certificados.sh 192.168.1.50 rpi5-vision rpi5-genai rpi5-agent uno-q esp32-env
# 2. Plataforma con la configuración de producción
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Los certificados se crean en `infra/mosquitto/certs/` (excluida del repositorio). La clave
`ca.key` permite emitir certificados nuevos y debe guardarse en un lugar seguro. En Windows el
script se ejecuta con Git Bash. La configuración de producción no carga los datos de demostración,
así que los dispositivos y los modelos se registran desde la consola.

### 8.2 Dar de alta el dispositivo

En la consola, **Dispositivos → Dar de alta** (solo el administrador). El identificador debe
coincidir exactamente con el que usará el dispositivo (`EDGE_DEVICE_ID`) y, con TLS, con el nombre
de su certificado. Los mensajes de un dispositivo que no está dado de alta se descartan y generan
una alerta. Con los datos de demostración ya existen los seis identificadores del laboratorio.

### 8.3 Raspberry Pi 5 y Arduino Uno Q

Las tres aplicaciones de `devices/` funcionan en cualquier placa con Linux de 64 bits. Requisitos:
Raspberry Pi OS de 64 bits (o el Debian del Uno Q) con Docker instalado
(`curl -fsSL https://get.docker.com | sh`).

```bash
git clone https://github.com/DavidN-v/app.git && cd app/devices
cp .env.example .env            # poner la IP del servidor (SERVER) y el resto de opciones
# Solo con TLS: copiar desde el servidor ca.crt, <dispositivo>.crt y <dispositivo>.key
mkdir -p certs && scp usuario@192.168.1.50:app/infra/mosquitto/certs/{ca.crt,rpi5-vision.crt,rpi5-vision.key} certs/
docker compose --profile vision up -d --build      # o --profile genai, o --profile agent
```

La primera construcción tarda bastante en la placa (descarga e instala las dependencias).
En una placa real no se definen `EDGE_BOARD_CPUS` ni `EDGE_BOARD_RAM_MB`: la telemetría mide el
equipo completo y la temperatura se lee del sensor del procesador.

**Cámara para `rpi5-vision`:**

- Cámara USB: `VISION_CAMERA=0` y `VISION_CAMERA_DEVICE=/dev/video0` en `devices/.env`.
- Módulo de cámara oficial (conector CSI): se emite el vídeo en la propia placa y el contenedor lo lee por red.

  ```bash
  rpicam-vid -t 0 --inline --listen --width 1280 --height 720 --framerate 10 -o tcp://0.0.0.0:8888
  ```

  y en `devices/.env`: `VISION_CAMERA=tcp://host.docker.internal:8888`.

Con cámara real no se simula la lente sucia; el drift aparece si las condiciones reales cambian
(poca luz, objetivo sucio, escena distinta de la de calibración). Conviene volver a medir la
distribución de referencia con la cámara definitiva, con la escena en condiciones normales:
`docker compose exec vision python calibrate.py`. El histograma que devuelve se incluye como
`reference_confidence_hist` en las métricas del modelo al registrarlo en la API (`POST /api/models`).

**Arduino Uno Q:** usa la aplicación de visión con su propio identificador y modelo:

```bash
VISION_DEVICE_ID=uno-q
VISION_MODEL_NAME=yolo-nano
VISION_MODEL_VERSION=8.1-int8
```

**Sin Docker** (o para otro programa propio): se instala el agente y se mide cada inferencia
desde el código del modelo.

```bash
pip install ./edge-agent
EDGE_DEVICE_ID=rpi5-vision EDGE_MQTT_HOST=192.168.1.50 edge-agent
```

```python
with agent.track_inference("yolo", "8.1") as t:
    outputs = session.run(None, {"images": frame})
    t.confidence = float(best_score)
```

Variables de conexión comunes a todos los programas de los dispositivos:

| Variable | Significado |
|---|---|
| `EDGE_DEVICE_ID` | identificador dado de alta en la plataforma |
| `EDGE_MQTT_HOST` / `EDGE_MQTT_PORT` | servidor y puerto (1883, o 8883 con TLS) |
| `EDGE_MQTT_TLS=1` | activa el cifrado |
| `EDGE_MQTT_CA`, `EDGE_MQTT_CERT`, `EDGE_MQTT_KEY` | certificado de la autoridad y certificado y clave del dispositivo |
| `EDGE_MQTT_USERNAME` / `EDGE_MQTT_PASSWORD` | usuario y contraseña, si el broker los pide |

### 8.4 ESP32

Material: placa ESP32 DevKit, pantalla OLED SSD1306 de 128×64 (I2C) y sensor Sensirion SCD40 o
SCD41 (temperatura, humedad y CO₂). Los dos módulos comparten el bus I2C:

| Módulo | VCC | GND | SDA | SCL |
|---|---|---|---|---|
| OLED SSD1306 | 3V3 | GND | GPIO 21 | GPIO 22 |
| Sensor SCD4x | 3V3 | GND | GPIO 21 | GPIO 22 |

Si el sensor no está conectado, el firmware lo indica por el monitor serie y usa valores simulados.

```bash
cd firmware/esp32
export WIFI_SSID=MiRed WIFI_PASS=clave MQTT_HOST=192.168.1.50
pio run -e esp32dev -t upload          # sin cifrar (opción A)
# Con TLS (opción B): primero el archivo de certificados, que no se sube al repositorio
./generar-certs-h.sh esp32-env
pio run -e esp32tls -t upload
pio device monitor                     # mensajes de WiFi, MQTT y cada inferencia
```

En PowerShell las variables se definen con `$env:WIFI_SSID="MiRed"` (y lo mismo para las demás).
Con TLS, el ESP32 sincroniza la hora por Internet antes de conectar, porque la necesita para
comprobar la validez de los certificados.

### 8.5 Arduino Ventuno

No hay un programa específico para el Ventuno. Si la placa ejecuta Linux, se usa el agente igual
que en el Uno Q. Si es un microcontrolador sin Linux, se toma como base el firmware del ESP32,
que ya implementa los mensajes que espera la plataforma (apartado 9).

### 8.6 Comprobar la conexión

- En la consola, el dispositivo pasa a **En línea** y sus cifras se actualizan cada pocos segundos.
- En la placa: `docker compose logs -f vision` debe mostrar `Conectado al broker (Success)`.
- En el servidor: `docker compose logs -f mosquitto` muestra cada conexión. Si aparece
  `not authorised`, el identificador no coincide con el nombre del certificado; si no aparece nada,
  revisar la IP del servidor y el cortafuegos.

### 8.7 Desplegar modelos en dispositivos físicos

1. Publicar el archivo del modelo en una dirección accesible desde el dispositivo (por ejemplo,
   un servidor HTTPS interno) y calcular su resumen: `sha256sum modelo.onnx`.
2. Registrarlo en **Modelos** con esa dirección y ese resumen; otra persona con rol de aprobador lo aprueba.
3. Desplegarlo en **Despliegues**. El dispositivo lo descarga, comprueba el resumen y lo pone en marcha.

Qué hace cada dispositivo al recibir un modelo:

| Dispositivo | Comportamiento |
|---|---|
| Visión (`rpi5-vision`, `uno-q`) | Carga el modelo ONNX nuevo sin reiniciarse y lo conserva tras un reinicio |
| GenAI | Rechaza el despliegue: el modelo de lenguaje se cambia reiniciando llama.cpp con el archivo nuevo |
| Agente de anomalías | Rechaza el despliegue: su detector forma parte del programa |
| ESP32 | Rechaza el despliegue: el modelo va dentro del firmware y se cambia reprogramando la placa |

En todos los casos de rechazo la plataforma registra el despliegue como fallido con el motivo, en
lugar de dar por instalado un modelo que no se está usando.

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

- Cambiar todos los secretos de `.env`: contraseñas de los usuarios (incluida `EG_VIEWER_PASSWORD`)
  y `EG_JWT_SECRET` con al menos 32 caracteres aleatorios.
- Usar la configuración con TLS del apartado 8.1 (opción B).
- Servir la consola y la API con HTTPS (por ejemplo, con un proxy inverso delante de nginx).
- Firmar los modelos y verificar la firma en el agente antes de instalarlos.
- Hacer copias de seguridad del volumen `postgres-data` y guardar `ca.key` fuera del servidor.
