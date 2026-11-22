"""Database models.

Importing this package registers every table with ``Base.metadata`` so that
Alembic autogeneration and test schema creation see the complete schema.
"""

from app.models.anomaly import AnomalyRecord
from app.models.energy import EnergyReading
from app.models.forecast import ForecastRecord

__all__ = ["AnomalyRecord", "EnergyReading", "ForecastRecord"]
