"""Configuración de la aplicación.

Todos los parámetros se leen de variables de entorno con el prefijo EG_ (por ejemplo,
EG_DATABASE_URL) o del archivo .env. Los valores que aparecen aquí son los usados por
defecto durante el desarrollo y deben cambiarse en una instalación real.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EG_", extra="ignore")

    # Base de datos: SQLite para desarrollo, PostgreSQL en el despliegue con Docker
    database_url: str = "sqlite:///./edge_governance.db"
    # Clave con la que se firman los tokens de sesión y su duración en minutos
    jwt_secret: str = "change-me-in-production-please-32b"
    jwt_ttl_minutes: int = 480

    # Conexión con el broker MQTT, por donde llegan los mensajes de los dispositivos
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    # Conexión cifrada con el broker (configuración de producción, puerto 8883). El broker exige
    # que la API se identifique con su propio certificado (nombre governance-api)
    mqtt_tls: bool = False
    mqtt_ca: str | None = None
    mqtt_cert: str | None = None
    mqtt_key: str | None = None

    # Segundos sin heartbeat antes de marcar un dispositivo como offline
    offline_after_s: int = 30
    # Cada cuántos segundos se recalcula el drift de los modelos
    drift_interval_s: int = 60
    # Orígenes web autorizados a llamar a la API desde el navegador
    cors_origins: list[str] = ["http://localhost:4200", "http://localhost:8080"]

    # Contraseñas iniciales de los usuarios que se crean en el primer arranque
    admin_password: str = "admin123"
    approver_password: str = "approver123"
    operator_password: str = "operator123"
    viewer_password: str = "viewer123"
    # Si es verdadero, en una base de datos vacía se cargan los dispositivos y modelos del laboratorio
    seed_demo_data: bool = True


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración. Se lee una sola vez y se reutiliza en toda la aplicación."""
    return Settings()
