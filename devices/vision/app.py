"""Raspberry Pi 5 · Visión artificial."""

import io
import json
import logging
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from edge_agent import connection
from edge_agent.agent import EdgeAgent
from edge_agent.deployer import ModelStore
from PIL import Image, ImageDraw, ImageFont

from detector import Detection, Detector
from sources import CameraSource, SceneSource

log = logging.getLogger("vision")

DEVICE_ID = os.getenv("EDGE_DEVICE_ID", "rpi5-vision")
MODEL_PATH = os.getenv("VISION_MODEL", "/models/yolov8n.onnx")
MODEL_NAME = os.getenv("VISION_MODEL_NAME", "yolo")
MODEL_VERSION = os.getenv("VISION_MODEL_VERSION", "8.1")
# Cámara real (número, /dev/videoN o URL de vídeo). Vacío = fotografías de prueba
CAMERA = os.getenv("VISION_CAMERA", "")
SCENES_DIR = Path(os.getenv("VISION_SCENES", "/scenes"))
TARGET_FPS = float(os.getenv("VISION_FPS", "2"))
SCENE_SECONDS = float(os.getenv("VISION_SCENE_SECONDS", "6"))
# Cada DIRTY_EVERY segundos, la lente se ensucia durante DIRTY_FOR segundos (0 = nunca)
DIRTY_EVERY = float(os.getenv("VISION_DIRTY_EVERY", "600"))
DIRTY_FOR = float(os.getenv("VISION_DIRTY_FOR", "60"))
PORT = int(os.getenv("VISION_PORT", "8101"))

PALETTE = ["#38bdf8", "#4af626", "#facc15", "#f472b6", "#c084fc", "#fb923c", "#34d399"]


class ActiveModel:

    def __init__(self, detector: Detector, name: str, version: str) -> None:
        self.lock = threading.Lock()
        self.detector, self.name, self.version = detector, name, version

    def get(self) -> tuple[Detector, str, str]:
        with self.lock:
            return self.detector, self.name, self.version

    def load(self, command: dict, path: Path) -> None:
        if command.get("framework", "onnx") != "onnx":
            raise ValueError(f"este dispositivo solo ejecuta modelos ONNX, no {command.get('framework')}")
        detector = Detector(str(path))  # si el archivo no es un modelo válido, falla aquí
        with self.lock:
            self.detector, self.name, self.version = detector, command["model"], command["version"]
        log.info("Modelo %s v%s cargado desde %s", command["model"], command["version"], path)


class Screen:

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


def annotate(frame: Image.Image, detections: list[Detection], font: ImageFont.ImageFont) -> Image.Image:
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


def inference_loop(agent: EdgeAgent, model: ActiveModel, source, screen: Screen) -> None:
    font = load_font(max(14, source.width // 40))
    frames, fps, fps_since = 0, 0.0, time.time()
    period = 1 / TARGET_FPS
    while True:
        t0 = time.time()
        frame, lens = source.read()
        detector, name, version = model.get()

        with agent.track_inference(name, version) as trace:
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
            "device": DEVICE_ID, "model": f"{name} {version} · ONNX Runtime",
            "objects": len(detections), "fps": round(fps, 1), "latency_ms": round(latency, 1),
            "lens": lens,
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if CAMERA:
        source = CameraSource(CAMERA)
    else:
        scenes = [Image.open(p).convert("RGB") for p in sorted(SCENES_DIR.glob("*.jpg"))]
        if not scenes:
            raise SystemExit(f"No hay escenas en {SCENES_DIR}")
        source = SceneSource(scenes, SCENE_SECONDS, DIRTY_EVERY, DIRTY_FOR)

    # Si un despliegue anterior instaló otro modelo, se arranca con ese y no con el de la imagen
    store = ModelStore(Path(os.getenv("EDGE_MODELS_DIR", "/data/models")))
    installed = store.manifest().get("current")
    if installed and Path(installed["path"]).exists():
        model = ActiveModel(Detector(installed["path"]), installed["model"], installed["version"])
    else:
        model = ActiveModel(Detector(MODEL_PATH), MODEL_NAME, MODEL_VERSION)
    log.info("Modelo %s v%s en marcha; imágenes de %s", model.name, model.version, CAMERA or SCENES_DIR)

    client = connection.create_client(DEVICE_ID)
    agent = EdgeAgent(DEVICE_ID, client, store,
                      float(os.getenv("EDGE_INTERVAL_S", "2")), loader=model.load)
    client.on_connect, client.on_message = agent.on_connect, agent.on_message
    connection.connect(client)

    screen = Screen()
    threading.Thread(target=inference_loop, args=(agent, model, source, screen), daemon=True).start()
    threading.Thread(target=agent.run, daemon=True).start()  # telemetría del sistema
    log.info("Pantalla local en http://0.0.0.0:%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(screen)).serve_forever()


if __name__ == "__main__":
    main()
