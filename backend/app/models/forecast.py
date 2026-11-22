"""Forecast prediction history."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ForecastRecord(Base):
    """A persisted point forecast produced by the Phase 4 model."""

    __tablename__ = "forecast_records"
    __table_args__ = (
        CheckConstraint(
            "forecast_horizon >= 1 AND forecast_horizon <= 48",
            name="ck_forecast_records_horizon_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    forecast_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        index=True,
    )
    predicted_energy_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    forecast_horizon: Mapped[int] = mapped_column(Integer, nullable=False)
