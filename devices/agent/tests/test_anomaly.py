import random

from anomaly import AnomalyDetector


def warm_up(det, device="uno-q", n=40, temp=40.0):
    rng = random.Random(1)
    for _ in range(n):
        det.observe(device, {"cpu": 10 + rng.uniform(-2, 2), "ram": 18 + rng.uniform(-1, 1), "temp": temp + rng.uniform(-1, 1)})


def test_no_verdict_without_history():
    v = AnomalyDetector().observe("uno-q", {"cpu": 99, "ram": 99, "temp": 99})
    assert v.anomalous is False
    assert v.normality == 1.0


def test_normal_reading_is_normal():
    det = AnomalyDetector()
    warm_up(det)
    v = det.observe("uno-q", {"cpu": 10.5, "ram": 18.2, "temp": 40.3})
    assert v.anomalous is False
    assert v.normality > 0.9


def test_temperature_spike_is_flagged():
    det = AnomalyDetector()
    warm_up(det)
    v = det.observe("uno-q", {"cpu": 10, "ram": 18, "temp": 70})
    assert v.anomalous is True
    assert v.worst_metric == "temp"
    assert v.z > 4
    assert v.normality < 0.4


def test_each_device_has_its_own_baseline():
    det = AnomalyDetector()
    warm_up(det, "uno-q", temp=40)
    warm_up(det, "rpi5-genai", temp=65)
    # 65 °C es normal para la GenAI pero una anomalía para el Uno Q
    assert det.observe("rpi5-genai", {"cpu": 10, "ram": 18, "temp": 65}).anomalous is False
    assert det.observe("uno-q", {"cpu": 10, "ram": 18, "temp": 65}).anomalous is True


def test_missing_metrics_are_ignored():
    det = AnomalyDetector()
    warm_up(det)
    assert det.observe("uno-q", {"cpu": 10, "ram": 18, "temp": None}).anomalous is False
