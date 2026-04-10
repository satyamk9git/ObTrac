"""
Backend configuration settings.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ObTrac"
    APP_VERSION: str = "0.1.0"
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
