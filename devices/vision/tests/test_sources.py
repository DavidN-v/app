import importlib.util
from pathlib import Path

import pytest
from PIL import Image
from sources import SceneSource, parse_camera


def test_camera_spec_accepts_index_path_and_url():
    assert parse_camera("0") == 0
    assert parse_camera(" 2 ") == 2
    assert parse_camera("/dev/video0") == "/dev/video0"
    assert parse_camera("tcp://192.168.1.20:8888") == "tcp://192.168.1.20:8888"


def test_scene_source_reports_clean_and_dirty_lens():
    scenes = [Image.new("RGB", (200, 100), "white")]
    clean = SceneSource(scenes, scene_seconds=6, dirty_every=0, dirty_for=0)
    frame, lens = clean.read()
    assert lens == "limpia" and frame.size[0] < 200
    always_dirty = SceneSource(scenes, scene_seconds=6, dirty_every=10, dirty_for=10)
    assert always_dirty.read()[1] == "sucia"


def test_active_model_rejects_formats_it_cannot_run():
    # Se carga por ruta: los demás dispositivos también tienen un módulo llamado app
    spec = importlib.util.spec_from_file_location("vision_app", Path(__file__).resolve().parents[1] / "app.py")
    vision_app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vision_app)

    model = vision_app.ActiveModel(detector=None, name="yolo", version="8.1")
    with pytest.raises(ValueError, match="ONNX"):
        model.load({"framework": "tflite", "model": "x", "version": "1"}, Path("x.tflite"))
    assert model.get()[1:] == ("yolo", "8.1")  # sigue en marcha el modelo anterior
