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

## Directory roles

| Directory | Purpose |
| --- | --- |
| `init/` | Future bootstrap SQL for roles/extensions. Not mounted in Phase 1. |
| `seeds/` | Small, documented reference datasets. No production data dumps. |

Phase 1 contains no domain tables. The initial Alembic revision is an empty
baseline that establishes the migration history.

## Connection details (local development)

- Host: `localhost`
- Port: `5432` (configurable through `POSTGRES_PORT`)
- Database: `ecopulse`
- User: `ecopulse`
- Password: local development value from `.env` / `backend/.env`

The Docker backend connects over the Compose network using host `db`. The
locally run backend connects through `localhost`.
