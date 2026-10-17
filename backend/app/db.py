"""Conexión con la base de datos mediante SQLAlchemy."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    """Clase base de la que heredan todas las tablas definidas en models.py."""


def make_engine(url: str):
    """Crea el motor de conexión adecuado según el tipo de base de datos.

    SQLite necesita que se permita usar la conexión desde varios hilos, y la base de datos
    en memoria (usada en las pruebas) debe compartir una única conexión. Para PostgreSQL se
    usa un grupo de conexiones reutilizables.
    """
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Abre una sesión por petición HTTP y la cierra al terminar, aunque haya un error."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
