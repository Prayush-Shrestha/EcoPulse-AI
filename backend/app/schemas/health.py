"""Pydantic response models for health checks."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

HealthStatus = Literal["ok", "degraded"]
CheckStatus = Literal["ok", "unavailable"]


class HealthCheck(BaseModel):
    status: CheckStatus
    latency_ms: float | None = Field(default=None, ge=0)
    detail: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: dict[str, HealthCheck]


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
