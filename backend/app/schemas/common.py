"""Shared schema types and validators."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field


def _ensure_naive_local(value: datetime) -> datetime:
    """Reject offset-aware values because the dataset uses local civil time."""

    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(
            "Use a naive local civil timestamp without a UTC offset; "
            "the source dataset has no timezone information."
        )
    return value


def _ensure_hour_aligned(value: datetime) -> datetime:
    if value.minute or value.second or value.microsecond:
        raise ValueError("The timestamp must be the start of a clock-hour.")
    return value


def _ensure_minute_aligned(value: datetime) -> datetime:
    if value.second or value.microsecond:
        raise ValueError("The timestamp must be aligned to a whole minute.")
    return value


LocalDatetime = Annotated[datetime, AfterValidator(_ensure_naive_local)]
HourAlignedDatetime = Annotated[
    datetime,
    AfterValidator(_ensure_naive_local),
    AfterValidator(_ensure_hour_aligned),
]
MinuteAlignedDatetime = Annotated[
    datetime,
    AfterValidator(_ensure_naive_local),
    AfterValidator(_ensure_minute_aligned),
]


class Pagination(BaseModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
