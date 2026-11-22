"""Shared service helpers."""

from __future__ import annotations

from datetime import datetime

from app.core.errors import RequestValidationError


def validate_time_range(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and start > end:
        raise RequestValidationError("The start timestamp must not be after the end timestamp.")
