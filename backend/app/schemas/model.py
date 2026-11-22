"""Schema for the model-information endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    key: Literal["forecasting", "anomaly_detection"]
    name: str
    version: str | None
    status: Literal["loaded", "unavailable"]
    model_type: str | None
    target: str | None
    feature_count: int | None = Field(default=None, ge=0)
    trained_at_utc: str | None
    metrics: dict[str, float] | None = None
    threshold: float | None = None
    raw_offset: float | None = None
    detail: str | None = None


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
    label_status: str | None = None
