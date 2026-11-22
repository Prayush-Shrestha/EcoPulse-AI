# ruff: noqa: E402 - environment must be configured before importing the app
"""Pytest fixtures for the Phase 5 integration suite.

Tests never touch the development database.  The session derives a dedicated
``*_test`` database from ``DATABASE_URL`` (or ``TEST_DATABASE_URL``), creates
it when necessary, recreates the schema with the SQLAlchemy metadata, and seeds
a real contiguous slice of the Phase 3 cleaned dataset.

Every test runs inside an outer transaction that is rolled back, so committed
service writes are isolated between tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
CLEANED_PARQUET = PROJECT_ROOT / "data" / "processed" / "household_power_cleaned.parquet"

SEED_START = "2010-11-15T00:00:00"
SEED_END = "2010-11-26T21:02:00"
PHASE4_FORECAST_TARGET_20 = 1.897491782047
PHASE4_ANOMALY_SCORE_2101 = 0.222983405
PHASE4_ANOMALY_SCORE_1920 = -0.018904202

SOURCE_TO_COLUMN = {
    "timestamp": "timestamp",
    "Global_active_power": "global_active_power",
    "Global_reactive_power": "global_reactive_power",
    "Voltage": "voltage",
    "Global_intensity": "global_intensity",
    "Sub_metering_1": "sub_metering_1",
    "Sub_metering_2": "sub_metering_2",
    "Sub_metering_3": "sub_metering_3",
    "energy_consumption_kwh": "energy_consumption_kwh",
    "is_imputed": "is_imputed",
}


def _test_database_url() -> URL:
    configured = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    base = (
        make_url(configured)
        if configured
        else make_url(str(Settings().database_url))
    )

    database = base.database or "ecopulse"
    if not database.endswith("_test"):
        database = f"{database}_test"
    if not database.endswith("_test"):  # defensive; should be unreachable
        raise RuntimeError("Refusing to use a test database without the _test suffix.")
    return base.set(database=database)


TEST_DATABASE_URL = _test_database_url()

SEED_REASON = (
    "data/processed/household_power_cleaned.parquet is missing. Run the Phase 3 "
    "pipeline first; data/processed is intentionally git-ignored."
)
MODELS_REASON = (
    "The Phase 4 Joblib artefacts are missing under machine-learning/models. Run "
    "the Phase 4 pipeline first; model binaries are intentionally git-ignored."
)

# Large artefacts are git-ignored, so a fresh clone cannot seed the test
# database or load the models. Tests that need them skip with an explicit
# reason instead of failing or, worse, inventing substitute data.
SEED_AVAILABLE = CLEANED_PARQUET.is_file()


def _model_artefact_paths() -> list[Path]:
    settings = Settings()
    return [
        settings.model_path(settings.forecast_model_file),
        settings.model_path(settings.forecast_metadata_file),
        settings.model_path(settings.forecast_features_file),
        settings.model_path(settings.anomaly_model_file),
        settings.model_path(settings.anomaly_metadata_file),
        settings.model_path(settings.anomaly_features_file),
    ]


MODELS_AVAILABLE = all(path.is_file() for path in _model_artefact_paths())


def _ensure_database(url: URL) -> None:
    """Create the test database if it does not exist."""

    admin_url = url.set(database="postgres", drivername="postgresql")
    with psycopg.connect(
        admin_url.render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (url.database,),
        ).fetchone()
        if exists is None:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database))
            )


# The application modules must see the test URL, not the development URL.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ["ENVIRONMENT"] = "test"

from app.db.base import Base  # noqa: E402
from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.energy import EnergyReading  # noqa: E402


def _load_seed_frame() -> pd.DataFrame:
    frame = pd.read_parquet(
        CLEANED_PARQUET,
        columns=list(SOURCE_TO_COLUMN),
        filters=[("timestamp", ">=", pd.Timestamp(SEED_START))],
    )
    frame = frame.loc[frame["timestamp"] <= pd.Timestamp(SEED_END)].copy()
    if frame.empty:
        raise RuntimeError("The Phase 3 dataset does not contain the expected test slice.")
    return frame


def _seed_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    renamed = frame.rename(columns=SOURCE_TO_COLUMN)
    records = renamed.to_dict(orient="records")
    for record in records:
        record["timestamp"] = record["timestamp"].to_pydatetime()
        record["is_imputed"] = bool(record["is_imputed"])
    return records


def _reset_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(engine)


def _insert_seed(engine: Engine, rows: list[dict[str, Any]], chunk_size: int = 5000) -> None:
    table = EnergyReading.__table__
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        with engine.begin() as connection:
            connection.execute(table.insert().values(chunk))


@pytest.fixture(scope="session")
def seed_frame() -> pd.DataFrame:
    if not SEED_AVAILABLE:
        pytest.skip(SEED_REASON)
    return _load_seed_frame()


@pytest.fixture(scope="session")
def seeded(seed_frame: pd.DataFrame) -> dict[str, Any]:
    frame = seed_frame.copy()
    frame["hour"] = frame["timestamp"].dt.floor("h")
    grouped = frame.groupby("hour").agg(
        rows=("energy_consumption_kwh", "size"),
        total=("energy_consumption_kwh", "sum"),
    )
    complete = grouped.loc[grouped["rows"] == 60]
    return {
        "frame": frame,
        "rows": len(frame),
        "start": frame["timestamp"].min().to_pydatetime(),
        "end": frame["timestamp"].max().to_pydatetime(),
        "total_energy_kwh": float(frame["energy_consumption_kwh"].sum()),
        "minimum_energy_kwh": float(frame["energy_consumption_kwh"].min()),
        "maximum_energy_kwh": float(frame["energy_consumption_kwh"].max()),
        "complete_hours": complete,
        "last_complete_hour": complete.index.max().to_pydatetime(),
        "first_complete_hour": complete.index.min().to_pydatetime(),
    }


@pytest.fixture(scope="session")
def _test_database(seed_frame: pd.DataFrame) -> Iterator[None]:
    _ensure_database(TEST_DATABASE_URL)
    _reset_schema(engine)
    _insert_seed(engine, _seed_rows(seed_frame))
    yield


@pytest.fixture()
def db_session(_test_database: None) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip model-dependent tests when the saved artefacts are unavailable."""

    if MODELS_AVAILABLE:
        return
    skip_models = pytest.mark.skip(reason=MODELS_REASON)
    for item in items:
        if "requires_models" in item.keywords:
            item.add_marker(skip_models)
