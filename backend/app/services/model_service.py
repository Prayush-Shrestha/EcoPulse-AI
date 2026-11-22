"""Read-only view of loaded ML models for health and documentation endpoints."""

from __future__ import annotations

from typing import Literal

from app.core.errors import NotFoundError
from app.ml.model_loader import ModelRegistry, get_model_registry
from app.schemas.model import ModelInfo, ModelListResponse

ModelKey = Literal["forecasting", "anomaly_detection"]

ANOMALY_LABEL_STATUS = (
    "Unsupervised deviation candidates; no labelled accuracy, precision, recall "
    "or F1 is claimed."
)


class ModelService:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or get_model_registry()

    def list_models(self) -> ModelListResponse:
        self.registry.load()
        return ModelListResponse(
            models=[
                self._forecast_info(),
                self._anomaly_info(),
            ],
            label_status=ANOMALY_LABEL_STATUS,
        )

    def get_model(self, key: str) -> ModelInfo:
        if key not in ("forecasting", "anomaly_detection"):
            raise NotFoundError(f"Unknown model key: {key}")
        return self.list_models().models[0 if key == "forecasting" else 1]

    def _forecast_info(self) -> ModelInfo:
        artifact = self.registry.forecast
        if artifact is None:
            return ModelInfo(
                key="forecasting",
                name="Forecasting model",
                version=None,
                status="unavailable",
                model_type=None,
                target=None,
                trained_at_utc=None,
                detail=self.registry.errors.get("forecasting"),
            )
        metrics = artifact.metadata.get("test_metrics") or {}
        selected_metrics = {
            key: float(metrics[key])
            for key in ("mae", "rmse", "r2", "mape_pct", "smape_pct")
            if key in metrics
        }
        return ModelInfo(
            key="forecasting",
            name=artifact.name,
            version=artifact.version,
            status="loaded",
            model_type=artifact.model_type,
            target=artifact.target,
            feature_count=len(artifact.feature_names),
            trained_at_utc=artifact.metadata.get("training_date_utc"),
            metrics=selected_metrics or None,
        )

    def _anomaly_info(self) -> ModelInfo:
        artifact = self.registry.anomaly
        if artifact is None:
            return ModelInfo(
                key="anomaly_detection",
                name="Anomaly-detection model",
                version=None,
                status="unavailable",
                model_type=None,
                target=None,
                trained_at_utc=None,
                detail=self.registry.errors.get("anomaly_detection"),
            )
        return ModelInfo(
            key="anomaly_detection",
            name=artifact.name,
            version=artifact.version,
            status="loaded",
            model_type=artifact.model_type,
            target="Global_active_power and multivariate context",
            feature_count=len(artifact.feature_names),
            trained_at_utc=artifact.metadata.get("training_date_utc"),
            threshold=artifact.threshold,
            raw_offset=artifact.raw_offset,
        )
