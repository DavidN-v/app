"""Configuración de la aplicación."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EG_", extra="ignore")

    database_url: str = "sqlite:///./edge_governance.db"
    jwt_secret: str = "change-me-in-production-please-32b"
    jwt_ttl_minutes: int = 480

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

    offline_after_s: int = 30
    drift_interval_s: int = 60
    cors_origins: list[str] = ["http://localhost:4200", "http://localhost:8080"]

    admin_password: str = "admin123"
    approver_password: str = "approver123"
    operator_password: str = "operator123"
    viewer_password: str = "viewer123"
    seed_demo_data: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
