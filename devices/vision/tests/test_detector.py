import numpy as np
import pytest
from PIL import Image

from detector import COCO_ES, letterbox, nms, postprocess


def yolo_output(*boxes):
    out = np.zeros((1, 84, len(boxes)), dtype=np.float32)
    for i, (cx, cy, w, h, cls, score) in enumerate(boxes):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4 + cls, i] = score
    return out


def test_coco_has_80_classes_in_spanish():
    assert len(COCO_ES) == 80
    assert COCO_ES[41] == "taza"
    assert COCO_ES[58] == "planta"


def test_letterbox_keeps_aspect_and_pads():
    tensor, scale, pad = letterbox(Image.new("RGB", (1280, 640)), 640)
    assert tensor.shape == (1, 3, 640, 640)
    assert scale == 0.5
    assert pad == (0, 160)
    assert 0 <= tensor.min() and tensor.max() <= 1


def test_postprocess_maps_boxes_back_to_original_image():
    # Imagen 1280x640 -> escala 0.5, relleno vertical 160
    out = yolo_output((320, 320, 100, 50, 41, 0.92))
    [d] = postprocess(out, scale=0.5, pad=(0, 160))
    assert d.label == "taza"
    assert d.score == pytest.approx(0.92)
    assert d.box == pytest.approx((540, 270, 740, 370))


def test_low_confidence_is_discarded():
    assert postprocess(yolo_output((320, 320, 50, 50, 0, 0.2)), 1.0, (0, 0), conf=0.35) == []


def test_nms_removes_duplicates_of_same_class_only():
    out = yolo_output(
        (100, 100, 50, 50, 41, 0.90),  # taza
        (102, 101, 50, 50, 41, 0.80),  # la misma taza, solapada: se elimina
        (101, 100, 50, 50, 58, 0.70),  # planta en el mismo sitio: otra clase, se queda
    )
    dets = postprocess(out, 1.0, (0, 0))
    assert [(d.label, round(d.score, 2)) for d in dets] == [("taza", 0.9), ("planta", 0.7)]


def test_nms_keeps_separate_objects():
    boxes = np.array([[0, 0, 10, 10], [100, 100, 110, 110]], dtype=np.float32)
    assert sorted(nms(boxes, np.array([0.9, 0.8]), 0.45)) == [0, 1]


def test_results_sorted_by_confidence():
    out = yolo_output((50, 50, 20, 20, 0, 0.5), (200, 200, 20, 20, 2, 0.9))
    assert [d.label for d in postprocess(out, 1.0, (0, 0))] == ["coche", "persona"]
