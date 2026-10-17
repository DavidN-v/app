import pytest

from assistant import Answer, build_messages, fleet_context, parse_completion

DEVICES = [
    {"id": "rpi5-genai", "name": "Raspberry Pi 5 (GenAI)", "status": "online", "cpu": 38.4, "temp": 64.2,
     "latency_ms": 42.0, "current_model": {"name": "qwen2.5-0.5b"}},
    {"id": "esp32-env", "name": "ESP32", "status": "offline", "cpu": None, "temp": None,
     "latency_ms": None, "current_model": None},
]
ALERTS = [
    {"severity": "critical", "message": "Temperatura alta en GenAI: 89.5 °C", "status": "open"},
    {"severity": "warning", "message": "Latencia elevada en Ventuno", "status": "resolved"},
]


def test_context_uses_real_values_and_marks_missing_ones():
    ctx = fleet_context(DEVICES, ALERTS)
    assert "Raspberry Pi 5 (GenAI) (rpi5-genai): online, modelo qwen2.5-0.5b, CPU 38%, temperatura 64°C" in ctx
    assert "ESP32 (esp32-env): offline, modelo ninguno, CPU —, temperatura sin sensor, latencia —" in ctx


def test_context_includes_precomputed_facts():
    ctx = fleet_context(DEVICES, ALERTS)
    assert "Más caliente: Raspberry Pi 5 (GenAI) con 64°C" in ctx
    assert "Mayor latencia: Raspberry Pi 5 (GenAI) con 42 ms" in ctx
    assert "Desconectados: ESP32" in ctx


def test_context_lists_only_open_alerts():
    ctx = fleet_context(DEVICES, ALERTS)
    assert "Alertas abiertas: 1" in ctx
    assert "[critical] Temperatura alta" in ctx
    assert "Ventuno" not in ctx


def test_messages_put_context_before_question():
    msgs = build_messages("¿Qué está caliente?", "CTX")
    assert msgs[0]["role"] == "system" and "español" in msgs[0]["content"]
    assert msgs[1]["content"].index("CTX") < msgs[1]["content"].index("¿Qué está caliente?")


def test_parse_completion_reads_llama_timings():
    body = {"choices": [{"message": {"content": "  Todo en orden.  "}}],
            "usage": {"completion_tokens": 40}, "timings": {"predicted_per_second": 25.5}}
    a = parse_completion(body, total_ms=2000)
    assert a.text == "Todo en orden."
    assert (a.tokens, a.tokens_per_s) == (40, 25.5)
    assert a.ms_per_token == 50


def test_parse_completion_without_timings_estimates_speed():
    body = {"choices": [{"message": {"content": "ok"}}], "usage": {"completion_tokens": 10}}
    assert parse_completion(body, total_ms=500).tokens_per_s == pytest.approx(20)


def test_ms_per_token_without_tokens_falls_back_to_total():
    assert Answer("", total_ms=300, tokens=0, tokens_per_s=0).ms_per_token == 300
