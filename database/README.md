# Database

PostgreSQL 17 is prepared through [`docker-compose.yml`](../docker-compose.yml).
The application database is local-only and is not exposed beyond the development
machine.

## Ownership of schema changes

Alembic migrations live with the backend because they are generated from the
SQLAlchemy metadata:

```text
backend/alembic/
```

Run migrations from the backend directory:

```powershell
cd D:\ai\EcoPulse-AI\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

Create a migration after changing models:

```powershell
alembic revision --autogenerate -m "describe the change"
```

Review every generated migration before applying it.

## Schema revisions

| Revision | Contents |
| --- | --- |
| `0001` | Empty Phase 1 baseline; establishes the migration history |
| `0002` | Phase 5 domain tables: `energy_readings`, `forecast_records`, `anomaly_records` |

`alembic current` should report `0002 (head)`.

### Tables (revision `0002`)

| Table | Contents | Key constraints |
| --- | --- | --- |
| `energy_readings` | Imported Phase 3 minute observations | Unique naive `timestamp`, non-negative checks |
| `forecast_records` | One row per generated forecast point | `forecast_horizon` between 1 and 48 |
| `anomaly_records` | One row per scoring decision | `detection_method`, `severity`, `is_anomaly` |

Energy, prediction and score columns use `Numeric(18, 9)` because minute energy
values are recurring decimals and coarser storage drifted hourly sums. Load the
data with the backend's duplicate-safe importer:

```powershell
cd D:\ai\EcoPulse-AI\backend
python scripts\import_processed_data.py
```

## Test database

The Pytest suite creates and uses a separate `ecopulse_test` database derived
from `DATABASE_URL` (or `TEST_DATABASE_URL`). It is rebuilt from SQLAlchemy
metadata and seeded with a real 17,103-row Phase 3 slice on each run, and it
never touches the development database.

## Directory roles

| Directory | Purpose |
| --- | --- |
| `init/` | Future bootstrap SQL for roles/extensions. Not mounted. |
| `seeds/` | Small, documented reference datasets. No production data dumps. |

## Connection details (local development)

- Host: `localhost`
- Port: `5433` in this checkout (configurable through `POSTGRES_PORT`; the
  published port avoids a collision with another local PostgreSQL on `5432`)
- Database: `ecopulse`
- User: `ecopulse`
- Password: local development value from `.env` / `backend/.env`

The Docker backend connects over the Compose network using host `db` and port
`5432`. The locally run backend connects through `localhost:5433`.
