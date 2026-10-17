"""Lógica del asistente: contexto de la flota + llamada al modelo de lenguaje local."""

import json
import time
import urllib.request
from dataclasses import dataclass

SYSTEM_PROMPT = (
    "Eres el asistente industrial de una flota de dispositivos edge. Respondes en español, "
    "en 2 o 3 frases, solo con los datos del contexto. Si algo no está en el contexto, dilo. "
    "No inventes cifras."
)


@dataclass
class Answer:
    text: str
    total_ms: float
    tokens: int
    tokens_per_s: float

    @property
    def ms_per_token(self) -> float:
        """Latencia por token generado: la métrica comparable entre modelos de lenguaje."""
        return self.total_ms / self.tokens if self.tokens else self.total_ms


def fleet_context(devices: list[dict], alerts: list[dict]) -> str:
    """Resume el estado real de la flota en texto compacto para el prompt."""
    lines = ["Dispositivos:"]
    for d in devices:
        model = d.get("current_model") or {}
        temp = f"{d['temp']:.0f}°C" if d.get("temp") is not None else "sin sensor"
        cpu = f"{d['cpu']:.0f}%" if d.get("cpu") is not None else "—"
        lat = f"{d['latency_ms']:.0f} ms" if d.get("latency_ms") is not None else "—"
        lines.append(
            f"- {d['name']} ({d['id']}): {d['status']}, modelo {model.get('name', 'ninguno')}, "
            f"CPU {cpu}, temperatura {temp}, latencia {lat}"
        )
    # Hechos ya calculados: un modelo pequeño los repite bien, pero no siempre los deduce bien
    with_temp = [d for d in devices if d.get("temp") is not None]
    with_lat = [d for d in devices if d.get("latency_ms") is not None]
    offline = [d["name"] for d in devices if d.get("status") != "online"]
    lines.append("Hechos calculados:")
    if with_temp:
        hot = max(with_temp, key=lambda d: d["temp"])
        lines.append(f"- Más caliente: {hot['name']} con {hot['temp']:.0f}°C")
    if with_lat:
        slow = max(with_lat, key=lambda d: d["latency_ms"])
        lines.append(f"- Mayor latencia: {slow['name']} con {slow['latency_ms']:.0f} ms")
    lines.append(f"- Desconectados: {', '.join(offline) if offline else 'ninguno'}")
    open_alerts = [a for a in alerts if a.get("status") != "resolved"]
    lines.append(f"Alertas abiertas: {len(open_alerts)}")
    for a in open_alerts[:6]:
        lines.append(f"- [{a['severity']}] {a['message']}")
    return "\n".join(lines)


def build_messages(question: str, context: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Contexto actual de la flota:\n{context}\n\nPregunta: {question}"},
    ]


def parse_completion(body: dict, total_ms: float) -> Answer:
    """Respuesta del endpoint OpenAI-compatible de llama.cpp, que añade `timings`."""
    text = body["choices"][0]["message"]["content"].strip()
    tokens = int(body.get("usage", {}).get("completion_tokens") or 0)
    timings = body.get("timings") or {}
    tps = float(timings.get("predicted_per_second") or (tokens / (total_ms / 1000) if total_ms else 0))
    return Answer(text=text, total_ms=total_ms, tokens=tokens, tokens_per_s=tps)


class LlamaClient:
    def __init__(self, base_url: str, max_tokens: int = 160, timeout: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout

    def ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=3) as r:
                return r.status == 200
        except OSError:
            return False

    def ask(self, messages: list[dict]) -> Answer:
        payload = json.dumps({
            "messages": messages, "max_tokens": self.max_tokens, "temperature": 0.3, "cache_prompt": True,
        }).encode()
        req = urllib.request.Request(f"{self.base_url}/v1/chat/completions", data=payload,
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            body = json.loads(r.read())
        return parse_completion(body, (time.perf_counter() - t0) * 1000)


class GovernanceClient:
    """Lee el estado de la flota de la API de gobernanza con una cuenta de solo lectura."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username, self.password = username, password
        self.token: str | None = None

    def _login(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/auth/login",
            data=json.dumps({"username": self.username, "password": self.password}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            self.token = json.loads(r.read())["access_token"]

    def _get(self, path: str):
        if not self.token:
            self._login()
        for attempt in range(2):
            req = urllib.request.Request(f"{self.base_url}{path}", headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    self._login()  # el token caducó
                    continue
                raise
        return None

    def snapshot(self) -> tuple[list[dict], list[dict]]:
        return self._get("/api/devices") or [], self._get("/api/alerts?status=open") or []
