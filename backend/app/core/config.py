"""
Backend configuration settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Cortexa"
    APP_VERSION: str = "0.6.8"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3100", "http://localhost:8501"]

    # File uploads
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # extra="ignore": this app's LLM/embedder credentials live in the
    # database (via the dashboard's LLM Config UI), not env vars — but
    # users still commonly keep provider keys (ANTHROPIC_API_KEY, etc.) in
    # a .env file for the SDK/demo apps to read directly. Without
    # extra="ignore", pydantic-settings' default (extra="forbid") means
    # ANY unrelated key in whatever .env file happens to be picked up
    # crashes the entire backend at import time — which is exactly what
    # happened when a provider key was added to the project's root .env
    # for an unrelated demo script.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
