"""EcoPulse AI FastAPI application factory.

The application loads the saved Phase 4 model artefacts once during startup,
reuses a process-wide SQLAlchemy engine, and converts every expected failure
into a consistent JSON error envelope.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import ApiError, DatabaseUnavailableError
from app.core.logging import configure_logging, request_id_var
from app.db.session import engine
from app.ml.model_loader import get_model_registry

settings = get_settings()
logger = logging.getLogger(__name__)

DESCRIPTION = """
Local-first backend for **EcoPulse AI**: intelligent energy consumption
monitoring, forecasting and anomaly detection.

The API serves the real Phase 3 processed dataset from PostgreSQL and performs
inference with the real Phase 4 saved models. Forecasts are recursive and use
only observed history plus earlier predictions, so no future readings leak into
a prediction.

* Forecasts and anomaly detections are persisted for history and analytics.
* Anomalies are *unsupervised deviation candidates*, not confirmed electricity
  faults; no labelled accuracy metrics are claimed.
* Timestamps are naive local civil time, exactly as stored in the source data.
"""


def _db_healthcheck() -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("database_connection_ok", extra={"dialect": engine.dialect.name})
    except Exception as exc:  # noqa: BLE001 - startup must report, not crash
        logger.error(
            "database_connection_failed",
            extra={"error": type(exc).__name__, "detail": str(exc)},
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    logger.info(
        "application_startup",
        extra={
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )
    _db_healthcheck()

    registry = get_model_registry()
    registry.load()
    logger.info(
        "model_registry_ready",
        extra={
            "forecast_loaded": registry.forecast is not None,
            "anomaly_loaded": registry.anomaly is not None,
            "forecast_model": registry.forecast.name if registry.forecast else None,
            "anomaly_model": registry.anomaly.name if registry.anomaly else None,
        },
    )
    if registry.errors:
        logger.warning("model_artefacts_incomplete", extra={"errors": registry.errors})

    try:
        yield
    finally:
        engine.dispose()
        logger.info("application_shutdown")


def _error_payload(code: str, message: str, details: object = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "details": details}}


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "EcoPulse AI",
            "url": "https://github.com/",
        },
        license_info={"name": "Portfolio project"},
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = round((perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": elapsed,
                },
            )
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_error_payload(
                    "internal_error",
                    "The request could not be completed.",
                ),
                headers={"X-Request-ID": request_id},
            )
            request_id_var.reset(token)
            return response

        elapsed = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log = logger.info if response.status_code < 400 else logger.warning
        log(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed,
            },
        )
        request_id_var.reset(token)
        return response

    @application.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "api_error",
                extra={
                    "code": exc.code,
                    "status_code": exc.status_code,
                    "detail": exc.message,
                },
            )
        else:
            logger.warning(
                "api_error",
                extra={"code": exc.code, "status_code": exc.status_code},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "location": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        logger.warning("validation_error", extra={"error_count": len(errors)})
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "validation_error",
                "The supplied values are invalid.",
                errors,
            ),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "not_found"
        elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "method_not_allowed"
        else:
            code = "http_error"
        message = (
            str(exc.detail)
            if exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
            else "The request could not be completed."
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, message),
            headers=exc.headers,
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("database_error", extra={"error": type(exc).__name__})
        error = DatabaseUnavailableError()
        return JSONResponse(
            status_code=error.status_code,
            content=_error_payload(error.code, error.message),
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        # Debug mode exposes the exception type only; never the traceback.
        logger.exception("unhandled_error", extra={"error": type(exc).__name__})
        detail = type(exc).__name__ if settings.debug else None
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_error",
                "The request could not be completed.",
                detail,
            ),
        )

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", include_in_schema=False)
    def api_root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "health": f"{settings.api_v1_prefix}/health",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return application


app = create_app()
