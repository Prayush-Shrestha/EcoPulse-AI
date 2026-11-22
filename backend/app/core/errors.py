"""Typed application errors with safe client-facing messages."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for expected API failures."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class RequestValidationError(ApiError):
    status_code = 422
    code = "validation_error"
    default_message = "The supplied values are invalid."


class InsufficientHistoryError(RequestValidationError):
    code = "insufficient_history"
    default_message = (
        "There is not enough continuous historical data to build the required features."
    )


class ModelUnavailableError(ApiError):
    status_code = 503
    code = "model_unavailable"
    default_message = "The required machine-learning model is not available."


class PredictionError(ApiError):
    status_code = 500
    code = "prediction_error"
    default_message = "The model could not produce a valid prediction."


class DatabaseUnavailableError(ApiError):
    status_code = 503
    code = "database_unavailable"
    default_message = "The database is not available."
