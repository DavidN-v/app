"""Actualización del esquema en instalaciones que ya tienen datos."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Columnas añadidas después de la primera versión: tabla -> {columna: definición SQL}
ADDED_COLUMNS = {
    "deployments": {"stage": "VARCHAR(16) NOT NULL DEFAULT 'requested'"},
}


def ensure_columns(engine: Engine) -> list[str]:
    added = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
    return added
