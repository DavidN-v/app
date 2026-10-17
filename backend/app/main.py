"""Punto de entrada de la API.

Crea la aplicación FastAPI, registra las rutas y define qué ocurre al arrancar y al parar:
se preparan las tablas, se cargan los datos iniciales, se conecta con el broker MQTT y se
lanzan las tareas periódicas (vigilancia de conexión, drift y despliegues).
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from sqlalchemy import text

from . import jobs, migrate, seed
from .config import get_settings
from .db import Base, SessionLocal, engine
from .hub import hub
from .mqtt_bridge import MqttBridge, NullBridge
from .routers import auth, deployments, devices, governance, live, metrics, models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class RedactTokens(logging.Filter):
    """Oculta el token de sesión en los registros del servidor.

    El canal en tiempo real (WebSocket) recibe el token en la dirección, y sin este filtro
    quedaría escrito en los registros de acceso, donde cualquiera con acceso podría copiarlo.
    """

    PATTERN = re.compile(r"(token=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                self.PATTERN.sub(r"\g<1>***", a) if isinstance(a, str) else a for a in record.args
            )
        record.msg = self.PATTERN.sub(r"\g<1>***", str(record.msg))
        return True


logging.getLogger("uvicorn.access").addFilter(RedactTokens())
logging.getLogger("uvicorn.error").addFilter(RedactTokens())


def create_app(start_background: bool = True) -> FastAPI:
    """Construye la aplicación. Las pruebas la crean sin tareas en segundo plano."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Arranque
        Base.metadata.create_all(engine)
        migrate.ensure_columns(engine)
        with SessionLocal() as db:
            seed.run(db)
        hub.bind_loop(asyncio.get_running_loop())
        app.state.bridge = MqttBridge() if settings.mqtt_enabled else NullBridge()
        app.state.bridge.start()
        stop = asyncio.Event()
        task = asyncio.create_task(jobs.run_forever(stop)) if start_background else None
        yield
        # Parada ordenada: primero las tareas periódicas y después la conexión MQTT
        stop.set()
        if task:
            await task
        app.state.bridge.stop()

    app = FastAPI(
        title="Edge Governance API",
        version="1.0.0",
        description="Gobernanza y observabilidad de modelos de IA en dispositivos edge",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    for r in (auth, devices, models, deployments, governance, live, metrics):
        app.include_router(r.router)
    app.mount("/metrics", make_asgi_app())

    @app.get("/healthz", tags=["ops"])
    def healthz():
        """Comprobación de salud usada por Docker: responde si la base de datos está accesible."""
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
