"""Loaded model metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.ml.model_loader import ModelRegistry, get_model_registry
from app.schemas.common import ErrorResponse
from app.schemas.model import ModelInfo, ModelListResponse
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models"])

Registry = Annotated[ModelRegistry, Depends(get_model_registry)]


@router.get(
    "",
    response_model=ModelListResponse,
    summary="List saved models and loading status",
    description=(
        "Report the real Phase 4 artefacts loaded by this process, including "
        "model versions, feature counts, selected metrics and anomaly threshold."
    ),
)
def list_models(registry: Registry) -> ModelListResponse:
    return ModelService(registry).list_models()


@router.get(
    "/{model_key}",
    response_model=ModelInfo,
    summary="Load status for one model",
    responses={404: {"model": ErrorResponse}},
)
def get_model(model_key: str, registry: Registry) -> ModelInfo:
    return ModelService(registry).get_model(model_key)
