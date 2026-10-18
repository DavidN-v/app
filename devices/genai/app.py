"""Raspberry Pi 5 · Modelo de lenguaje (dispositivo real en contenedor)."""

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

from assistant import GovernanceClient, LlamaClient, build_messages, fleet_context

log = logging.getLogger("genai")

DEVICE_ID = os.getenv("EDGE_DEVICE_ID", "rpi5-genai")
MODEL_NAME = os.getenv("GENAI_MODEL_NAME", "qwen2.5-0.5b")
MODEL_VERSION = os.getenv("GENAI_MODEL_VERSION", "q4_k_m")
AUTO_ASK_S = float(os.getenv("GENAI_AUTO_ASK_S", "20"))
PORT = int(os.getenv("GENAI_PORT", "8102"))
AUTO_QUESTIONS = [
    "¿Cuál es el estado general de la flota?",
    "¿Hay algún dispositivo con temperatura alta?",
    "¿Qué alertas están abiertas y cuál es la más grave?",
    "¿Qué dispositivo tiene la mayor latencia?",
    "¿Todos los dispositivos están en línea?",
]


class Assistant:

    def __init__(self, agent: EdgeAgent, llm: LlamaClient, gov: GovernanceClient) -> None:
        self.agent, self.llm, self.gov = agent, llm, gov
        self.lock = threading.Lock()  # el modelo atiende una pregunta a la vez, como en la placa
        self.history: deque = deque(maxlen=30)
        self.last_user_ask = 0.0
        self.stats = {"tokens_per_s": None, "ms_per_token": None, "total_ms": None, "answers": 0}

    def ask(self, question: str, source: str) -> dict:
        with self.lock:
            try:
                devices, alerts = self.gov.snapshot()
                context = fleet_context(devices, alerts)
            except Exception as exc:  # la API puede no estar lista todavía
                context = "No hay datos de la flota disponibles ahora mismo."
                log.warning("Sin contexto de la flota: %s", exc)
            try:
                answer = self.llm.ask(build_messages(question, context))
            except Exception as exc:
                entry = {"q": question, "a": f"El modelo no respondió: {exc}", "source": source, "error": True, "ts": time.time()}
                self.history.append(entry)
                return entry
            # Se reporta la latencia por token (comparable entre modelos y con el umbral de la política)
            self.agent.publish("inference", {
                "model": MODEL_NAME, "version": MODEL_VERSION,
                "latency_ms": round(answer.ms_per_token, 2), "confidence": None,
                "tokens": answer.tokens, "tokens_per_s": round(answer.tokens_per_s, 2),
                "total_ms": round(answer.total_ms, 1),
            })
            self.stats = {
                "tokens_per_s": round(answer.tokens_per_s, 1), "ms_per_token": round(answer.ms_per_token, 1),
                "total_ms": round(answer.total_ms), "answers": self.stats["answers"] + 1,
            }
            entry = {"q": question, "a": answer.text, "source": source, "error": False, "ts": time.time(),
                     "tokens": answer.tokens, "seconds": round(answer.total_ms / 1000, 2)}
            self.history.append(entry)
            return entry

    def auto_loop(self) -> None:
        i = 0
        while True:
            time.sleep(AUTO_ASK_S)
            if not self.llm.ready() or time.time() - self.last_user_ask < AUTO_ASK_S:
                continue  # si un humano está preguntando, el operador automático espera
            self.ask(AUTO_QUESTIONS[i % len(AUTO_QUESTIONS)], "auto")
            i += 1


PAGE = (Path(__file__).parent / "screen.html").read_bytes()


def reject_hot_swap(command: dict, path: Path) -> None:
    raise RuntimeError("el modelo de lenguaje se cambia reiniciando el servidor llama.cpp con el "
                       "nuevo archivo (variables del servicio genai-llm)")


def make_handler(assistant: Assistant):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE)
            elif self.path == "/state":
                body = {"model": f"{MODEL_NAME} ({MODEL_VERSION}) · llama.cpp", "ready": assistant.llm.ready(),
                        "busy": assistant.lock.locked(), "stats": assistant.stats, "history": list(assistant.history)}
                self._send(200, "application/json", json.dumps(body).encode())
            elif self.path == "/healthz":
                self._send(200, "text/plain", b"ok")
            else:
                self._send(404, "text/plain", b"no encontrado")

        def do_POST(self) -> None:
            if self.path != "/ask":
                self._send(404, "text/plain", b"no encontrado")
                return
            length = min(int(self.headers.get("Content-Length", 0)), 4000)
            try:
                question = str(json.loads(self.rfile.read(length) or b"{}").get("question", "")).strip()[:500]
            except ValueError:
                question = ""
            if not question:
                self._send(400, "application/json", b'{"error":"Escribe una pregunta"}')
                return
            assistant.last_user_ask = time.time()
            self._send(200, "application/json", json.dumps(assistant.ask(question, "user")).encode())

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = connection.create_client(DEVICE_ID)
    agent = EdgeAgent(DEVICE_ID, client, ModelStore(Path(os.getenv("EDGE_MODELS_DIR", "/data/models"))),
                      float(os.getenv("EDGE_INTERVAL_S", "2")), loader=reject_hot_swap)
    client.on_connect, client.on_message = agent.on_connect, agent.on_message
    connection.connect(client)

    assistant = Assistant(
        agent,
        LlamaClient(os.getenv("LLM_URL", "http://localhost:8080")),
        GovernanceClient(os.getenv("GOV_API_URL", "http://localhost:8000"),
                         os.getenv("GOV_USER", "viewer"), os.getenv("GOV_PASSWORD", "viewer123")),
    )
    threading.Thread(target=agent.run, daemon=True).start()
    threading.Thread(target=assistant.auto_loop, daemon=True).start()
    log.info("Pantalla local en http://0.0.0.0:%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), make_handler(assistant)).serve_forever()


if __name__ == "__main__":
    main()
