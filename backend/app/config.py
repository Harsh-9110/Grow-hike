from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+psycopg://grow:grow_dev_only@db:5432/grow"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "local-only-change-before-deployment-32-bytes-minimum"
    encryption_key: str = ""
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    cookie_secure: bool = False
    access_minutes: int = 10
    refresh_days: int = 7
    demo_mode: bool = True
    demo_email: str = "demo@growhike.dev"
    demo_password: str = "GrowHike-Demo-2026!"
    quote_ttl: int = 60
    stale_seconds: int = 604800
    alpha_vantage_key: str = ""
    twelve_data_key: str = ""
    yahoo_per_minute: int = 30
    yahoo_per_day: int = 2000
    google_client_id: str = ""
    google_client_secret: str = ""
    kite_api_key: str = ""
    kite_api_secret: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    def validate_production(self) -> None:
        if self.environment == "production":
            if self.demo_mode or not self.cookie_secure:
                raise ValueError("Production requires DEMO_MODE=false and COOKIE_SECURE=true")
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("local-only"):
                raise ValueError("Set a random JWT_SECRET of at least 32 characters")
            if not self.frontend_url.startswith("https://") or not self.encryption_key:
                raise ValueError("Production requires HTTPS and ENCRYPTION_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
