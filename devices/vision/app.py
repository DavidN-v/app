"""Raspberry Pi 5 · Visión artificial (dispositivo real en contenedor).

- Ejecuta YOLOv8n con ONNX Runtime sobre escenas reales (imágenes de COCO val2017).
- Publica telemetría, latencia y confianza reales en la plataforma vía el agente edge.
- Sirve su pantalla local en http://<host>:8101 con el vídeo anotado.
- Incidente programado: la "lente se ensucia" (desenfoque y poca luz) y la confianza del modelo
  baja de verdad, lo que la plataforma detecta como drift.
"""

import io
import json
import logging
import os
import random
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt
from edge_agent.agent import EdgeAgent
from edge_agent.deployer import ModelStore
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from detector import Detection, Detector

log = logging.getLogger("vision")

DEVICE_ID = os.getenv("EDGE_DEVICE_ID", "rpi5-vision")
MODEL_PATH = os.getenv("VISION_MODEL", "/models/yolov8n.onnx")
MODEL_NAME, MODEL_VERSION = "yolo", os.getenv("VISION_MODEL_VERSION", "8.1")
SCENES_DIR = Path(os.getenv("VISION_SCENES", "/scenes"))
TARGET_FPS = float(os.getenv("VISION_FPS", "4"))
SCENE_SECONDS = float(os.getenv("VISION_SCENE_SECONDS", "6"))
# Cada DIRTY_EVERY segundos, la lente se ensucia durante DIRTY_FOR segundos (0 = nunca)
DIRTY_EVERY = float(os.getenv("VISION_DIRTY_EVERY", "300"))
DIRTY_FOR = float(os.getenv("VISION_DIRTY_FOR", "60"))
PORT = int(os.getenv("VISION_PORT", "8101"))

PALETTE = ["#38bdf8", "#4af626", "#facc15", "#f472b6", "#c084fc", "#fb923c", "#34d399"]


class Screen:
    """Estado compartido entre el bucle de inferencia y la pantalla web."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jpeg: bytes = b""
        self.frame_id = 0
        self.stats: dict = {}
        self.history: deque = deque(maxlen=60)

    def update(self, jpeg: bytes, stats: dict) -> None:
        with self.lock:
            self.jpeg, self.stats = jpeg, stats
            self.frame_id += 1
            self.history.append(stats["latency_ms"])

    def snapshot(self) -> tuple[int, bytes, dict, list]:
        with self.lock:
            return self.frame_id, self.jpeg, dict(self.stats), list(self.history)


def load_font(size: int) -> ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def camera_frame(scene: Image.Image, dirty: bool) -> Image.Image:
    """Simula la cámara: encuadre que tiembla un poco, luz que varía y, si toca, lente sucia."""
    w, h = scene.size
    dx, dy = random.randint(0, w // 20), random.randint(0, h // 20)
    frame = scene.crop((dx, dy, w - w // 20 + dx, h - h // 20 + dy))
    frame = ImageEnhance.Brightness(frame).enhance(random.uniform(0.9, 1.1))
    if dirty:
        frame = frame.filter(ImageFilter.GaussianBlur(random.uniform(5, 8)))
        frame = ImageEnhance.Brightness(frame).enhance(0.45)
        frame = ImageEnhance.Contrast(frame).enhance(0.6)
    return frame


def annotate(frame: Image.Image, detections: list[Detection], font: ImageFont.ImageFont) -> Image.Image:
    """Dibuja sobre el fotograma una caja y una etiqueta por cada objeto detectado."""
    img = frame.convert("RGB")
    draw = ImageDraw.Draw(img)
    stroke = max(2, img.width // 300)
    for i, d in enumerate(detections):
        color = PALETTE[i % len(PALETTE)]
        x1, y1, x2, y2 = d.box
        draw.rectangle((x1, y1, x2, y2), outline=color, width=stroke)
        text = f"{d.label} {d.score:.2f}"
        tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        ty = max(0, y1 - th - 6)
        draw.rectangle((x1, ty, x1 + tw + 10, ty + th + 6), fill=color)
        draw.text((x1 + 5, ty + 3), text, fill="#000000", font=font)
    return img


def inference_loop(agent: EdgeAgent, detector: Detector, scenes: list[Image.Image], screen: Screen) -> None:
    """Bucle principal: genera un fotograma, lo analiza, informa a la plataforma y actualiza la pantalla.
    Se cambia de escena cada SCENE_SECONDS segundos y se mantiene el ritmo de TARGET_FPS."""
    font = load_font(max(14, scenes[0].width // 40))
    start = time.time()
    scene_idx, scene_since = 0, time.time()
    frames, fps, fps_since = 0, 0.0, time.time()
    period = 1 / TARGET_FPS
    while True:
        t0 = time.time()
        if t0 - scene_since > SCENE_SECONDS:
            scene_idx, scene_since = (scene_idx + 1) % len(scenes), t0
        elapsed = t0 - start
        dirty = DIRTY_EVERY > 0 and (elapsed % DIRTY_EVERY) > (DIRTY_EVERY - DIRTY_FOR)
        frame = camera_frame(scenes[scene_idx], dirty)

        with agent.track_inference(MODEL_NAME, MODEL_VERSION) as trace:
            detections = detector(frame)
            # La confianza que se reporta es la del objeto más claro: es la que vigila el drift
            trace.confidence = round(detections[0].score, 3) if detections else 0.05
        latency = (time.time() - t0) * 1000

        frames += 1
        if time.time() - fps_since >= 1:
            fps, frames, fps_since = frames / (time.time() - fps_since), 0, time.time()

        buf = io.BytesIO()
        annotate(frame, detections, font).save(buf, format="JPEG", quality=80)
        screen.update(buf.getvalue(), {
            "device": DEVICE_ID, "model": f"YOLOv8n ({MODEL_NAME} {MODEL_VERSION}) · ONNX Runtime",
            "objects": len(detections), "fps": round(fps, 1), "latency_ms": round(latency, 1),
            "lens": "sucia" if dirty else "limpia",
            "detections": [{"label": d.label, "score": round(d.score, 3)} for d in detections[:8]],
        })
        time.sleep(max(0.0, period - (time.time() - t0)))


PAGE = (Path(__file__).parent / "screen.html").read_bytes()


def make_handler(screen: Screen):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silencio: la pantalla pide datos sin parar
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE)
            elif self.path == "/stats":
                _, _, stats, history = screen.snapshot()
                self._send(200, "application/json", json.dumps({**stats, "history": history}).encode())
            elif self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                last = -1
                try:
                    while True:
                        fid, jpeg, _, _ = screen.snapshot()
                        if fid != last and jpeg:
                            last = fid
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    return
            elif self.path == "/healthz":
                self._send(200, "text/plain", b"ok")
            else:
                self._send(404, "text/plain", b"no encontrado")

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    """Carga el modelo y las escenas, conecta con MQTT y arranca la pantalla web."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scenes = [Image.open(p).convert("RGB") for p in sorted(SCENES_DIR.glob("*.jpg"))]
    if not scenes:
        raise SystemExit(f"No hay escenas en {SCENES_DIR}")
    detector = Detector(MODEL_PATH)
    log.info("Modelo %s cargado; %d escenas", MODEL_PATH, len(scenes))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"device-{DEVICE_ID}")
    client.will_set(f"edge/{DEVICE_ID}/status", "offline", qos=1, retain=True)
    agent = EdgeAgent(DEVICE_ID, client, ModelStore(Path(os.getenv("EDGE_MODELS_DIR", "/data/models"))),
                      float(os.getenv("EDGE_INTERVAL_S", "2")))
    client.on_connect, client.on_message = agent.on_connect, agent.on_message
    client.reconnect_delay_set(1, 30)
    client.connect_async(os.getenv("EDGE_MQTT_HOST", "localhost"), int(os.getenv("EDGE_MQTT_PORT", "1883")), 30)
    client.loop_start()

    screen = Screen()
    threading.Thread(target=inference_loop, args=(agent, detector, scenes, screen), daemon=True).start()
    threading.Thread(target=agent.run, daemon=True).start()  # telemetría del sistema
    log.info("Pantalla local en http://0.0.0.0:%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(screen)).serve_forever()


if __name__ == "__main__":
    main()
