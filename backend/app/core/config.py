from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "EcoPulse AI API"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+psycopg://ecopulse:ecopulse_local_dev@localhost:5432/ecopulse"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800
    database_connect_timeout_seconds: int = 5
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Relative paths resolve from backend/; absolute paths are used as provided.
    ml_models_dir: str = "../machine-learning/models"
    forecast_model_file: str = "forecasting/best_forecasting_model.joblib"
    forecast_metadata_file: str = "forecasting/forecasting_metadata.json"
    forecast_features_file: str = "forecasting/forecasting_features.json"
    anomaly_model_file: str = "anomaly_detection/isolation_forest.joblib"
    anomaly_metadata_file: str = "anomaly_detection/anomaly_metadata.json"
    anomaly_features_file: str = "anomaly_detection/anomaly_features.json"

    import_batch_size: int = 5000
    import_progress_every: int = 10

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg:// driver")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalised = value.upper()
        if normalised not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalised

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_ml_models_dir(self) -> Path:
        path = Path(self.ml_models_dir)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path.resolve()

    def model_path(self, relative_name: str) -> Path:
        return self.resolved_ml_models_dir / relative_name


@lru_cache
def get_settings() -> Settings:
    return Settings()
