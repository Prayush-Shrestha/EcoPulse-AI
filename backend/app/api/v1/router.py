from fastapi import APIRouter

from app.api.v1.endpoints import analytics, anomalies, energy, forecasts, health, models

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(energy.router)
api_router.include_router(forecasts.router)
api_router.include_router(anomalies.router)
api_router.include_router(analytics.router)
api_router.include_router(models.router)
