"""Mide la distribución de confianza de referencia de YOLO con la lente limpia.

El drift (PSI) compara lo que ve el modelo en producción con esta referencia, así que debe salir
de este mismo modelo sobre estas mismas escenas, no de una distribución supuesta.

Uso dentro del contenedor:
    python calibrate.py [muestras_por_escena]
Imprime el histograma en JSON con los mismos bins que el backend (0.0-1.0 en pasos de 0.1).
"""

import json
import sys

from PIL import Image

from app import MODEL_PATH, SCENES_DIR, camera_frame
from detector import Detector

BINS = [i / 10 for i in range(10)] + [1.0000001]


def main() -> None:
    per_scene = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    detector = Detector(MODEL_PATH)
    scenes = [Image.open(p).convert("RGB") for p in sorted(SCENES_DIR.glob("*.jpg"))]
    counts = [0] * 10
    for scene in scenes:
        for _ in range(per_scene):
            detections = detector(camera_frame(scene, dirty=False))
            conf = detections[0].score if detections else 0.05  # igual que en inference_loop
            counts[next(i for i in range(10) if BINS[i] <= conf < BINS[i + 1])] += 1
    total = sum(counts)
    # Suavizado de Laplace (+0.5 por bin): una franja sin muestras en la calibración no es
    # imposible en producción, y con probabilidad 0 una sola detección dispararía el PSI
    hist = [(c + 0.5) / (total + 5) for c in counts]
    print(json.dumps({"samples": total, "hist": [round(h, 4) for h in hist]}))


if __name__ == "__main__":
    main()
