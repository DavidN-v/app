"""Mide la distribución de confianza de referencia de YOLO en condiciones normales."""

import json
import sys

from PIL import Image

from app import CAMERA, MODEL_PATH, SCENES_DIR
from detector import Detector
from sources import CameraSource, camera_frame

BINS = [i / 10 for i in range(10)] + [1.0000001]


def frames(samples: int):
    if CAMERA:
        camera = CameraSource(CAMERA)
        for _ in range(samples):
            yield camera.read()[0]
        return
    scenes = [Image.open(p).convert("RGB") for p in sorted(SCENES_DIR.glob("*.jpg"))]
    for i in range(samples):
        yield camera_frame(scenes[i % len(scenes)], dirty=False)


def main() -> None:
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    detector = Detector(MODEL_PATH)
    counts = [0] * 10
    for frame in frames(samples):
        detections = detector(frame)
        conf = detections[0].score if detections else 0.05  # igual que en inference_loop
        counts[next(i for i in range(10) if BINS[i] <= conf < BINS[i + 1])] += 1
    total = sum(counts)
    # Suavizado de Laplace (+0.5 por intervalo): una franja sin muestras en la calibración no es
    # imposible en producción, y con probabilidad 0 una sola detección dispararía el PSI
    hist = [(c + 0.5) / (total + 5) for c in counts]
    print(json.dumps({"samples": total, "hist": [round(h, 4) for h in hist]}))


if __name__ == "__main__":
    main()
