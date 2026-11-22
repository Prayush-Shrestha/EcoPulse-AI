"""Minute-level energy readings imported from the Phase 3 cleaned dataset."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnergyReading(Base):
    """One observed or interpolated minute of household power consumption.

    Timestamps are naive local civil time, matching the immutable Phase 3
    dataset. No UTC offset or daylight-saving conversion is invented here.
    """

    __tablename__ = "energy_readings"
    __table_args__ = (
        CheckConstraint(
            "global_active_power >= 0",
            name="ck_energy_readings_global_active_power_non_negative",
        ),
        CheckConstraint(
            "global_reactive_power >= 0",
            name="ck_energy_readings_global_reactive_power_non_negative",
        ),
        CheckConstraint("voltage > 0", name="ck_energy_readings_voltage_positive"),
        CheckConstraint(
            "global_intensity >= 0",
            name="ck_energy_readings_global_intensity_non_negative",
        ),
        CheckConstraint(
            "sub_metering_1 >= 0",
            name="ck_energy_readings_sub_metering_1_non_negative",
        ),
        CheckConstraint(
            "sub_metering_2 >= 0",
            name="ck_energy_readings_sub_metering_2_non_negative",
        ),
        CheckConstraint(
            "sub_metering_3 >= 0",
            name="ck_energy_readings_sub_metering_3_non_negative",
        ),
        CheckConstraint(
            "energy_consumption_kwh >= 0",
            name="ck_energy_readings_energy_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        unique=True,
        index=True,
    )
    global_active_power: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    global_reactive_power: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    voltage: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    global_intensity: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    sub_metering_1: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sub_metering_2: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    sub_metering_3: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    energy_consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    is_imputed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
