from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    app_name: str = "Sports Analytics Pipeline"
    app_env: str = "development"
    log_level: str = "INFO"

    # Database
    postgres_user: str = "sports_user"
    postgres_password: str = "changeme"
    postgres_db: str = "sports_analytics"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str | None = None

    # API Keys
    cfbd_api_key: str = ""
    highlightly_api_key: str = ""
    anthropic_api_key: str = ""

    # CORS
    backend_cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("database_url", mode="before")
    @classmethod
    def build_database_url(cls, v, info):
        if v:
            return v
        data = info.data
        user = data.get("postgres_user", "sports_user")
        password = data.get("postgres_password", "changeme")
        host = data.get("postgres_host", "db")
        port = data.get("postgres_port", 5432)
        db = data.get("postgres_db", "sports_analytics")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()