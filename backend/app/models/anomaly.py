"""Unsupervised anomaly-detection history."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Identity,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnomalyRecord(Base):
    """A scored minute.

    ``is_anomaly`` marks a statistical deviation candidate. It does not assert
    that the observation is a confirmed electricity fault.
    """

    __tablename__ = "anomaly_records"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    observation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        index=True,
    )
    energy_consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    anomaly_score: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
