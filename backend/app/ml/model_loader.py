"""Load the saved Phase 4 model artefacts exactly once per process."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.core.config import Settings, get_settings
from app.core.errors import ModelUnavailableError

logger = logging.getLogger(__name__)


class ModelArtifactError(RuntimeError):
    """Raised when a saved model cannot be loaded or validated."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Metadata file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ModelArtifactError(f"Metadata must be a JSON object: {path}")
    return document


def _require_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing model files: " + ", ".join(missing))


@dataclass
class ForecastArtifact:
    path: Path
    bundle: dict[str, Any]
    metadata: dict[str, Any]
    feature_document: dict[str, Any]

    @property
    def model(self) -> Any:
        return self.bundle["model"]

    @property
    def feature_names(self) -> list[str]:
        return list(self.feature_document["features"])

    @property
    def name(self) -> str:
        return str(self.metadata.get("model_name", self.bundle.get("model_name", "unknown")))

    @property
    def version(self) -> str:
        return str(
            self.metadata.get("model_version", self.bundle.get("model_version", "unknown"))
        )

    @property
    def model_type(self) -> str:
        return str(self.metadata.get("model_type", type(self.model).__name__))

    @property
    def target(self) -> str:
        return str(self.metadata.get("target_variable", self.bundle.get("target", "")))

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if list(features.columns) != self.feature_names:
            raise ModelArtifactError(
                "Forecast feature order does not match the saved model definition."
            )
        preprocessor = self.bundle.get("preprocessor")
        transformed = preprocessor.transform(features) if preprocessor is not None else features
        values = np.asarray(self.model.predict(transformed), dtype=np.float64)
        if values.shape != (len(features),):
            raise ModelArtifactError("Forecast model returned an unexpected shape.")
        return values


@dataclass
class AnomalyArtifact:
    path: Path
    bundle: dict[str, Any]
    metadata: dict[str, Any]
    feature_document: dict[str, Any]
    scaler: Any = field(init=False)

    def __post_init__(self) -> None:
        self.scaler = self.bundle.get("scaler")
        if self.scaler is None:
            raise ModelArtifactError("Anomaly bundle does not contain its fitted scaler.")

    @property
    def model(self) -> Any:
        return self.bundle["model"]

    @property
    def feature_names(self) -> list[str]:
        return list(self.feature_document["features"])

    @property
    def name(self) -> str:
        return str(self.metadata.get("model_name", self.bundle.get("model_name", "unknown")))

    @property
    def version(self) -> str:
        return str(
            self.metadata.get("model_version", self.bundle.get("model_version", "unknown"))
        )

    @property
    def model_type(self) -> str:
        return str(self.metadata.get("model_type", type(self.model).__name__))

    @property
    def threshold(self) -> float:
        """Decision-function threshold, which is 0 for a fitted Isolation Forest.

        The bundle also stores scikit-learn's raw ``offset_`` (the
        ``score_samples`` threshold); it is intentionally not exposed as the
        decision threshold because the API scores with ``decision_function``.
        """

        return 0.0

    @property
    def raw_offset(self) -> float:
        return float(self.bundle["threshold"])

    def score(self, features: pd.DataFrame) -> tuple[float, bool]:
        if list(features.columns) != self.feature_names:
            raise ModelArtifactError(
                "Anomaly feature order does not match the saved model definition."
            )
        scaled = self.scaler.transform(features.to_numpy(dtype=np.float64))
        score = float(self.model.decision_function(scaled)[0])
        prediction = int(self.model.predict(scaled)[0])
        is_anomaly = prediction == -1
        if is_anomaly != (score < self.threshold):
            logger.warning(
                "Anomaly score and prediction disagree at the decision threshold",
                extra={
                    "score": score,
                    "threshold": self.threshold,
                    "prediction": prediction,
                },
            )
        return score, is_anomaly


class ModelRegistry:
    """Thread-safe registry that loads both artefacts once."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.forecast: ForecastArtifact | None = None
        self.anomaly: AnomalyArtifact | None = None
        self.errors: dict[str, str] = {}
        self.loaded_at_utc: str | None = None
        self._lock = threading.Lock()
        self._loaded = False

    def load(self, *, force: bool = False) -> None:
        with self._lock:
            if self._loaded and not force:
                return
            started = time.perf_counter()
            self.errors.clear()
            self.forecast = self._load_forecast()
            self.anomaly = self._load_anomaly()
            self.loaded_at_utc = pd.Timestamp.now(tz="UTC").isoformat()
            self._loaded = True
            logger.info(
                "model_registry_loaded",
                extra={
                    "forecast_loaded": self.forecast is not None,
                    "anomaly_loaded": self.anomaly is not None,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )

    def _load_forecast(self) -> ForecastArtifact | None:
        paths = [
            self.settings.model_path(self.settings.forecast_model_file),
            self.settings.model_path(self.settings.forecast_metadata_file),
            self.settings.model_path(self.settings.forecast_features_file),
        ]
        try:
            _require_files(paths)
            bundle = joblib.load(paths[0])
            metadata = _load_json(paths[1])
            features = _load_json(paths[2])
            if not isinstance(bundle, dict) or "model" not in bundle:
                raise ModelArtifactError("Forecast bundle must contain a fitted model.")
            bundle_features = list(bundle.get("feature_names", []))
            document_features = list(features.get("features", []))
            if bundle_features != document_features:
                raise ModelArtifactError(
                    "Forecast bundle and feature document disagree on feature order."
                )
            artifact = ForecastArtifact(paths[0], bundle, metadata, features)
            logger.info(
                "forecast_model_loaded",
                extra={"model": artifact.name, "version": artifact.version},
            )
            return artifact
        except Exception as exc:  # noqa: BLE001 - model availability must not crash startup
            self.errors["forecasting"] = str(exc)
            logger.warning(
                "forecast_model_unavailable",
                extra={"error": type(exc).__name__, "detail": str(exc)},
            )
            return None

    def _load_anomaly(self) -> AnomalyArtifact | None:
        paths = [
            self.settings.model_path(self.settings.anomaly_model_file),
            self.settings.model_path(self.settings.anomaly_metadata_file),
            self.settings.model_path(self.settings.anomaly_features_file),
        ]
        try:
            _require_files(paths)
            bundle = joblib.load(paths[0])
            metadata = _load_json(paths[1])
            features = _load_json(paths[2])
            if not isinstance(bundle, dict) or "model" not in bundle:
                raise ModelArtifactError("Anomaly bundle must contain a fitted model.")
            bundle_features = list(bundle.get("feature_names", []))
            document_features = list(features.get("features", []))
            if bundle_features != document_features:
                raise ModelArtifactError(
                    "Anomaly bundle and feature document disagree on feature order."
                )
            artifact = AnomalyArtifact(paths[0], bundle, metadata, features)
            logger.info(
                "anomaly_model_loaded",
                extra={"model": artifact.name, "version": artifact.version},
            )
            return artifact
        except Exception as exc:  # noqa: BLE001 - model availability must not crash startup
            self.errors["anomaly_detection"] = str(exc)
            logger.warning(
                "anomaly_model_unavailable",
                extra={"error": type(exc).__name__, "detail": str(exc)},
            )
            return None

    def require_forecast(self) -> ForecastArtifact:
        self.load()
        if self.forecast is None:
            raise ModelUnavailableError(
                "The forecasting model is unavailable.",
                details={"reason": self.errors.get("forecasting", "unknown")},
            )
        return self.forecast

    def require_anomaly(self) -> AnomalyArtifact:
        self.load()
        if self.anomaly is None:
            raise ModelUnavailableError(
                "The anomaly-detection model is unavailable.",
                details={"reason": self.errors.get("anomaly_detection", "unknown")},
            )
        return self.anomaly


_registry: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_model_registry() -> ModelRegistry:
    """Return the process-wide registry without loading models implicitly."""

    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ModelRegistry()
        return _registry
