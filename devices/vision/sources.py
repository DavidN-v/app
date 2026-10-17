"""Origen de las imágenes que analiza el dispositivo de visión.

- SceneSource: fotografías fijas que simulan una cámara (encuadre que tiembla, luz variable y,
  de forma programada, una lente sucia). Es la opción por defecto en la emulación.
- CameraSource: una cámara real. Se activa con la variable VISION_CAMERA, que admite:
    0, 1...              número de una cámara USB
    /dev/video0          ruta del dispositivo de vídeo en Linux
    tcp://... rtsp://... http://...   vídeo por red, por ejemplo el que emite rpicam-vid con el
                         módulo de cámara oficial de Raspberry Pi
"""

import logging
import random
import time

from PIL import Image, ImageEnhance, ImageFilter

log = logging.getLogger("vision")


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


class SceneSource:
    """Recorre las escenas cambiando cada `scene_seconds` y ensucia la lente de forma periódica:
    cada `dirty_every` segundos, durante `dirty_for` segundos (dirty_every = 0 lo desactiva)."""

    def __init__(self, scenes: list[Image.Image], scene_seconds: float, dirty_every: float,
                 dirty_for: float) -> None:
        self.scenes, self.scene_seconds = scenes, scene_seconds
        self.dirty_every, self.dirty_for = dirty_every, dirty_for
        self.start = self.scene_since = time.time()
        self.index = 0

    @property
    def width(self) -> int:
        return self.scenes[0].width

    def read(self) -> tuple[Image.Image, str]:
        """Devuelve el fotograma y el estado de la lente que se muestra en la pantalla."""
        now = time.time()
        if now - self.scene_since > self.scene_seconds:
            self.index, self.scene_since = (self.index + 1) % len(self.scenes), now
        elapsed = now - self.start
        dirty = self.dirty_every > 0 and (elapsed % self.dirty_every) > (self.dirty_every - self.dirty_for)
        return camera_frame(self.scenes[self.index], dirty), "sucia" if dirty else "limpia"


def parse_camera(spec: str) -> int | str:
    """Convierte el valor de VISION_CAMERA en lo que espera OpenCV: un número o una ruta/URL."""
    spec = spec.strip()
    return int(spec) if spec.isdigit() else spec


class CameraSource:
    """Cámara real leída con OpenCV. Si la cámara deja de responder, se vuelve a abrir."""

    def __init__(self, spec: str) -> None:
        import cv2  # solo hace falta con cámara real

        self.cv2 = cv2
        self.target = parse_camera(spec)
        self.capture = None
        self.width = 1280
        self._open()

    def _open(self) -> None:
        if self.capture is not None:
            self.capture.release()
        self.capture = self.cv2.VideoCapture(self.target)
        if self.capture.isOpened():
            self.width = int(self.capture.get(self.cv2.CAP_PROP_FRAME_WIDTH)) or self.width
            log.info("Cámara %s abierta", self.target)
        else:
            log.warning("No se pudo abrir la cámara %s; se reintentará", self.target)

    def read(self) -> tuple[Image.Image, str]:
        ok, frame = self.capture.read() if self.capture is not None else (False, None)
        while not ok:
            time.sleep(2)
            self._open()
            ok, frame = self.capture.read()
        # OpenCV entrega los colores en orden BGR; la red y la pantalla esperan RGB
        return Image.fromarray(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)), "cámara"
