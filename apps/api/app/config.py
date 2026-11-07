from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione letta dalle variabili d'ambiente (vedi .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field(default="development", description="development | test | production")

    # Database. L'API usa un ruolo senza privilegi (soggetto a RLS);
    # le migrazioni usano il ruolo proprietario dello schema.
    database_url: str = "postgresql+psycopg://redazione_app:app@localhost:5442/redazione"
    migrations_database_url: str = "postgresql+psycopg://redazione:owner@localhost:5442/redazione"

    # Chiave per cifrare i segreti a riposo (es. seed TOTP). Fernet, base64 urlsafe 32 byte.
    secret_key: str = Field(default="", description="Generare con: python -m app.cli gen-key")

    # Sessioni
    session_cookie_name: str = "redazione_session"
    session_ttl_hours: int = 12
    session_mfa_pending_minutes: int = 10
    cookie_secure: bool = False  # True in produzione (solo HTTPS)

    # Origini autorizzate per CORS e controllo CSRF (Origin header)
    allowed_origins: list[str] = ["http://localhost:5173"]

    # Storage S3 compatibile (SeaweedFS in sviluppo)
    s3_endpoint_url: str = "http://localhost:8333"
    s3_access_key: str = "redazione"
    s3_secret_key: str = "redazione-secret"
    s3_bucket: str = "redazione-sources"
    s3_region: str = "eu-south-1"

    max_upload_mb: int = 1024

    totp_issuer: str = "Redazione"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
