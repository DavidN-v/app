"""Punto de entrada de la API."""

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
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        # Primero las tareas periódicas y después MQTT
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
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
