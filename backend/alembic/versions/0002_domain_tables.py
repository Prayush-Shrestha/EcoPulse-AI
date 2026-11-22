"""Add Phase 5 domain tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19

Creates the three persistence tables used by the API:

* ``energy_readings`` stores imported Phase 3 minute observations.
* ``forecast_records`` stores each model-generated forecast point.
* ``anomaly_records`` stores each Isolation Forest scoring decision.

All timestamps for measurements and forecasts are naive local civil time to
match the immutable Phase 3 dataset. Audit timestamps (``created_at`` and
``detected_at``) are timezone-aware server timestamps.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "energy_readings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("global_active_power", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column(
            "global_reactive_power", sa.Numeric(precision=10, scale=3), nullable=False
        ),
        sa.Column("voltage", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("global_intensity", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("sub_metering_1", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sub_metering_2", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("sub_metering_3", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("energy_consumption_kwh", sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column(
            "is_imputed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "global_active_power >= 0",
            name="ck_energy_readings_global_active_power_non_negative",
        ),
        sa.CheckConstraint(
            "global_reactive_power >= 0",
            name="ck_energy_readings_global_reactive_power_non_negative",
        ),
        sa.CheckConstraint("voltage > 0", name="ck_energy_readings_voltage_positive"),
        sa.CheckConstraint(
            "global_intensity >= 0",
            name="ck_energy_readings_global_intensity_non_negative",
        ),
        sa.CheckConstraint(
            "sub_metering_1 >= 0",
            name="ck_energy_readings_sub_metering_1_non_negative",
        ),
        sa.CheckConstraint(
            "sub_metering_2 >= 0",
            name="ck_energy_readings_sub_metering_2_non_negative",
        ),
        sa.CheckConstraint(
            "sub_metering_3 >= 0",
            name="ck_energy_readings_sub_metering_3_non_negative",
        ),
        sa.CheckConstraint(
            "energy_consumption_kwh >= 0",
            name="ck_energy_readings_energy_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_energy_readings_timestamp"),
        "energy_readings",
        ["timestamp"],
        unique=True,
    )

    op.create_table(
        "forecast_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("forecast_timestamp", sa.DateTime(), nullable=False),
        sa.Column("predicted_energy_kwh", sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("forecast_horizon", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "forecast_horizon >= 1 AND forecast_horizon <= 48",
            name="ck_forecast_records_horizon_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_forecast_records_created_at"),
        "forecast_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_forecast_records_forecast_timestamp"),
        "forecast_records",
        ["forecast_timestamp"],
        unique=False,
    )

    op.create_table(
        "anomaly_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observation_timestamp", sa.DateTime(), nullable=False),
        sa.Column("energy_consumption_kwh", sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column("anomaly_score", sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column("detection_method", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_anomaly_records_detected_at"),
        "anomaly_records",
        ["detected_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_anomaly_records_observation_timestamp"),
        "anomaly_records",
        ["observation_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_anomaly_records_observation_timestamp"),
        table_name="anomaly_records",
    )
    op.drop_index(op.f("ix_anomaly_records_detected_at"), table_name="anomaly_records")
    op.drop_table("anomaly_records")

    op.drop_index(
        op.f("ix_forecast_records_forecast_timestamp"),
        table_name="forecast_records",
    )
    op.drop_index(op.f("ix_forecast_records_created_at"), table_name="forecast_records")
    op.drop_table("forecast_records")

    op.drop_index(op.f("ix_energy_readings_timestamp"), table_name="energy_readings")
    op.drop_table("energy_readings")
