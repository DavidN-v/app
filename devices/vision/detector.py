"""Detector de objetos YOLOv8 ejecutado con ONNX Runtime."""

from dataclasses import dataclass

import numpy as np
from PIL import Image

# Clases COCO en el orden del modelo, traducidas para la pantalla local
COCO_ES = [
    "persona", "bicicleta", "coche", "moto", "avión", "autobús", "tren", "camión", "barco",
    "semáforo", "hidrante", "señal de stop", "parquímetro", "banco", "pájaro", "gato", "perro",
    "caballo", "oveja", "vaca", "elefante", "oso", "cebra", "jirafa", "mochila", "paraguas",
    "bolso", "corbata", "maleta", "frisbee", "esquís", "snowboard", "pelota", "cometa",
    "bate", "guante", "monopatín", "tabla de surf", "raqueta", "botella", "copa", "taza",
    "tenedor", "cuchillo", "cuchara", "cuenco", "plátano", "manzana", "sándwich", "naranja",
    "brócoli", "zanahoria", "perrito caliente", "pizza", "dónut", "tarta", "silla", "sofá",
    "planta", "cama", "mesa", "inodoro", "televisor", "portátil", "ratón", "mando",
    "teclado", "móvil", "microondas", "horno", "tostadora", "fregadero", "nevera", "libro",
    "reloj", "jarrón", "tijeras", "peluche", "secador", "cepillo de dientes",
]


@dataclass
class Detection:

    label: str
    score: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 en píxeles de la imagen original


def letterbox(img: Image.Image, size: int) -> tuple[np.ndarray, float, tuple[int, int]]:
    w, h = img.size
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    pad = ((size - nw) // 2, (size - nh) // 2)
    canvas.paste(img.convert("RGB").resize((nw, nh), Image.BILINEAR), pad)
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    return tensor, scale, pad


def iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (box[2] - box[0]) * (box[3] - box[1])
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return inter / np.maximum(area + areas - inter, 1e-9)


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        order = rest[iou(boxes[i], boxes[rest]) < threshold]
    return keep


def postprocess(output: np.ndarray, scale: float, pad: tuple[int, int], conf: float = 0.35,
                iou_threshold: float = 0.45, labels: list[str] = COCO_ES) -> list[Detection]:
    preds = output[0].T  # (anclas, 4 + clases)
    class_scores = preds[:, 4:]
    cls = class_scores.argmax(axis=1)
    score = class_scores[np.arange(len(cls)), cls]
    mask = score >= conf
    if not mask.any():
        return []
    preds, cls, score = preds[mask], cls[mask], score[mask]
    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad[0]) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad[1]) / scale

    detections: list[Detection] = []
    for c in np.unique(cls):  # NMS por clase
        idx = np.where(cls == c)[0]
        for k in nms(boxes[idx], score[idx], iou_threshold):
            i = idx[k]
            name = labels[c] if c < len(labels) else str(c)
            detections.append(Detection(name, float(score[i]), tuple(float(v) for v in boxes[i])))
    return sorted(detections, key=lambda d: d.score, reverse=True)


class Detector:

    def __init__(self, model_path: str, size: int = 640, conf: float = 0.35) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4  # los 4 núcleos de una Raspberry Pi 5
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        self.size = size
        self.conf = conf

    def __call__(self, img: Image.Image) -> list[Detection]:
        tensor, scale, pad = letterbox(img, self.size)
        output = self.session.run(None, {self.input: tensor})[0]
        return postprocess(output, scale, pad, self.conf)
