# Development

Operating instructions for the local EcoPulse AI stack (Phases 1-5).

---

## 1. Verified environment

The initial scaffold was created and inspected on this machine:

| Tool | Verified version | Notes |
| --- | --- | --- |
| Windows | Windows 11 | Local-only runtime target |
| Node.js | 22.23.4 | Next.js 16 requires Node.js 20.9+ |
| npm | 10.9.9 | Lockfile is committed |
| Python | 3.13.4 | Backend supports 3.11-3.13; containers use 3.12 |
| Git | 2.50.0 | Repository initialised locally |
| Docker | 29.6.1 | Docker Desktop, WSL 2 backend |
| Docker Compose | 5.1.4 | Compose v2 syntax |
| Java | 17.0.20 LTS | Required by future PySpark work |
| PostgreSQL | 17 (container) | Published on host port `5433`; not installed natively |
| FastAPI / Pydantic | 0.163.1 / 2.14.3 | Backend API stack |
| SQLAlchemy / Alembic / Psycopg | 2.0.58 / 1.20.1 / 3.3.9 | Synchronous ORM, migrations, Psycopg 3 driver |
| Backend inference stack | pandas 2.3.3, NumPy 2.5.5, scikit-learn 1.9.1, Joblib 1.6.0, PyArrow 26.0.1 | Pinned to the Phase 4 training versions |
| Pytest / Ruff | 9.2.0 / 0.17.5 | Backend quality gates |
| scikit-learn (ML env) | 1.9.1 | Dedicated `machine-learning/.venv` |
| ML data stack | pandas 2.3.3, NumPy 2.5.5, PyArrow 26.0.1, Joblib 1.6.0 | Same ML environment |
| nbconvert | 7.17.2 | Executes the Phase 2-4 notebooks |

The backend virtual environment deliberately carries the same pandas, NumPy,
scikit-learn, Joblib and PyArrow versions as `machine-learning/.venv`, so served
predictions match the saved Phase 4 models. It never imports
`machine-learning/` or `data-engineering/` code.

### Compatibility notes

- **Airflow does not run natively on Windows.** It will be added as a Linux
  container in a later phase. Do not `pip install apache-airflow` into the
  backend virtual environment.
- **Python 3.13 is the local interpreter, but the backend image uses 3.12.**
  This avoids unnecessary image/runtime surprises and is compatible with the
  future Airflow container. The application code targets Python 3.11+.
- **PySpark 4.3 needs Java 17.** Java 17 is installed, but Spark is not part of
  the current install because no Spark job exists yet.
- **Machine learning uses its own environment.** Install the Phase 4 packages
  only into `machine-learning/.venv`; the backend and data-engineering
  environments are separate. The notebook kernel is `ecopulse-ml`, and on this
  machine Jupyter needed `JUPYTER_PATH` set because a backend kernelspec shim
  resolved before the ML environment.
- **Docker Desktop must be running** before Compose commands. Both images were
  built locally after the daemon started, and the full stack reached a healthy
  state: Alembic revision applied, the health endpoint reported `ok` for the
  API and database, and the interface rendered the live status panel. CI
  still validates Compose configuration only. If Docker Desktop stops mid-run,
  PostgreSQL connections fail with `connection timeout expired`; restart the
  engine and wait for the `db` container to report healthy before retrying.
- **PostgreSQL publishes host port `5433`** in this checkout so it does not
  collide with other local databases (another PostgreSQL already occupies
  `5432`). A native `backend/.env` must therefore use `localhost:5433`; inside
  the Compose network the backend still uses `db:5432`.
- `next.config.ts` uses `output: "standalone"` for a small production image.
- `NEXT_PUBLIC_API_URL` is embedded at build time in the frontend container. It
  must be reachable from the browser on the host, normally
  `http://localhost:8000`.

---

## 2. One-time setup

### Docker Compose route

```powershell
cd D:\ai\EcoPulse-AI
Copy-Item .env.example .env
# Start Docker Desktop, wait for the engine, then:
docker compose up --build
```

If the host already uses port 5432, 8000, or 3000, change `POSTGRES_PORT`,
`API_PORT`, or `FRONTEND_PORT` in `.env`. Also update `NEXT_PUBLIC_API_URL` if
the API port changes.

### Native route

```powershell
cd D:\ai\EcoPulse-AI
docker compose up -d db

# Backend
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Set DATABASE_URL to localhost:5433 (the host port published by db).
alembic upgrade head
python scripts\import_processed_data.py      # 2,049,356 rows, idempotent
uvicorn app.main:app --reload --port 8000

# Frontend in a second terminal
cd ..\frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

The import step loads `data/processed/household_power_cleaned.parquet` into
`energy_readings`. It is safe to re-run: existing timestamps are skipped and the
summary reports exactly how many rows were inserted. Without it the API still
starts, but energy endpoints return empty results.

URLs:

- Interface: http://localhost:3000
- Swagger UI: http://localhost:8000/docs
- Health JSON: http://localhost:8000/api/v1/health

The interface can be started before the backend. Its status panel will show an
offline API and retry every 30 seconds.

### Phase 4 machine-learning route

The four Phase 3 Parquet outputs must exist in `data/processed/` before running
the pipeline:

```powershell
cd D:\ai\EcoPulse-AI\machine-learning
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd D:\ai\EcoPulse-AI
machine-learning\.venv\Scripts\python.exe machine-learning\src\06_run_ml_pipeline.py
```

The pipeline validates the Phase 3 inputs, prepares both datasets, trains and
evaluates the forecasting candidates, fits the anomaly detectors, reloads both
saved models, and writes six reports plus twelve figures. The verified local run
took about 163 seconds and passed 128/128 checks.

The executed notebooks read saved artefacts and do not retrain the models.
Register the ML kernel once, then execute either notebook:

```powershell
cd D:\ai\EcoPulse-AI
machine-learning\.venv\Scripts\python.exe -m ipykernel install `
  --prefix machine-learning\.venv --name ecopulse-ml `
  --display-name "EcoPulse ML (Python 3.13)"

$env:JUPYTER_PATH = "$PWD\machine-learning\.venv\share\jupyter"
machine-learning\.venv\Scripts\python.exe -m nbconvert --to notebook --execute `
  --inplace --ExecutePreprocessor.timeout=900 `
  --ExecutePreprocessor.kernel_name=ecopulse-ml `
  data-engineering\notebooks\03_energy_forecasting.ipynb
```

Use `python -m nbconvert` rather than `python -m jupyter nbconvert` in the ML
environment. On this machine the latter dispatched through a backend virtual
environment shim and could not find the ML kernel.

---

## 3. Environment files

| File | Scope |
| --- | --- |
| `.env` | Docker Compose interpolation (database credentials, ports, CORS) |
| `backend/.env` | Native backend process |
| `frontend/.env.local` | Native Next.js process |

All are ignored by Git. The matching `.env.example` files are committed.

Backend settings are case-insensitive. Passing real environment variables
overrides values in `.env`, which is how Compose and CI inject configuration.

---

## 4. Database workflow

```powershell
cd D:\ai\EcoPulse-AI\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
alembic current            # expect: 0002 (head)
```

Revisions:

| Revision | Contents |
| --- | --- |
| `0001` | Empty Phase 1 baseline (migration history only) |
| `0002` | `energy_readings`, `forecast_records`, `anomaly_records` |

Create a revision after changing SQLAlchemy models:

```powershell
alembic revision --autogenerate -m "add energy readings"
```

Always review an autogenerated migration; Alembic does not guarantee safe or
complete DDL for every change.

### Test database

Pytest never uses the development database. The suite derives a dedicated
`ecopulse_test` database from `DATABASE_URL` (or `TEST_DATABASE_URL`), recreates
the schema from SQLAlchemy metadata, and seeds it with a real 17,103-row Phase 3
slice (`2010-11-15T00:00:00` … `2010-11-26T21:02:00`). Each test runs inside an
outer transaction that is rolled back, so writes never leak between tests.
CI provisions the same database through a PostgreSQL service container.

Reset the local database completely (destructive):

```powershell
cd D:\ai\EcoPulse-AI
docker compose down -v
docker compose up -d db
```

Then run `alembic upgrade head` again and re-import the dataset with
`python scripts\import_processed_data.py`.

---

## 5. Quality gates

```powershell
cd D:\ai\EcoPulse-AI\backend
.\.venv\Scripts\Activate.ps1
ruff check .
pytest

cd ..\frontend
npm run lint
npm run typecheck
npm run build

cd ..
docker compose --env-file .env.example config --quiet

# Phase 4 pipeline and saved-model verification
machine-learning\.venv\Scripts\python.exe machine-learning\src\06_run_ml_pipeline.py
```

The backend tests require a running PostgreSQL (the `db` container on port
`5433`); they use the dedicated `ecopulse_test` database and never the
development data. `data/processed/` and the Joblib model binaries are
Git-ignored, so a fresh clone skips the tests that need them with an explicit
reason instead of failing:

```text
SKIPPED ... The Phase 4 Joblib artefacts are missing under machine-learning/models.
SKIPPED ... data/processed/household_power_cleaned.parquet is missing.
```

Verified locally with all artefacts present: `ruff check .` clean and
`55 passed`. Without the models: `28 passed, 27 skipped`. Without the Parquet
seed: `12 passed, 43 skipped`. All runs exit `0`.

CI applies migrations against a real PostgreSQL service and runs the same
quality gates; artefact-dependent tests skip there for the same reason.

The machine-learning pipeline requires the Phase 3 Parquet outputs and writes
only to `data/processed/ml/`, `machine-learning/models/` and
`reports/machine-learning/`. It exits non-zero if any validation or saved-model
check fails.

Run `npm ci` instead of `npm install` when validating the committed lockfile.

---

## 6. Common issues

### `docker` cannot connect to the engine

Start Docker Desktop and wait until it reports that the engine is running. Then
retry `docker info`.

### `connection timeout expired ... port 5433`

The Docker engine (and therefore PostgreSQL) stopped while the backend was
running. Start Docker Desktop, wait for `ecopulse-ai-db-1` to report `healthy`,
then retry. Imported data survives because it lives in the Compose volume; the
import script can be re-run safely at any time.

### PowerShell blocks venv activation

Run once in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

Or invoke the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### Port already in use

Change the relevant host port in `.env` / `backend/.env` /
`frontend/.env.local`. If you change the API port, rebuild the frontend container
so `NEXT_PUBLIC_API_URL` is embedded again.

### The status panel says "API is not reachable"

1. Confirm `http://localhost:8000/api/v1/health` responds in a browser.
2. Confirm `NEXT_PUBLIC_API_URL` matches the browser-visible API URL.
3. Confirm `CORS_ORIGINS` contains the exact frontend origin.
4. If using Compose, rebuild after changing `NEXT_PUBLIC_API_URL`.

### Database health is degraded

```powershell
docker compose ps
docker compose logs db
```

The API stays available by design; only readiness returns `503`.

### `DATABASE_URL must use the postgresql+psycopg:// driver`

The backend intentionally rejects other drivers. Use the Psycopg 3 SQLAlchemy
URL format shown in the example files.

### `nbconvert` cannot find the `ecopulse-ml` kernel

`jupyter kernelspec list` may resolve the backend environment on this machine.
Use the ML environment directly and point Jupyter at its data directory:

```powershell
$env:JUPYTER_PATH = "D:\ai\EcoPulse-AI\machine-learning\.venv\share\jupyter"
machine-learning\.venv\Scripts\python.exe -m nbconvert --to notebook --execute `
  --inplace --ExecutePreprocessor.kernel_name=ecopulse-ml `
  data-engineering\notebooks\04_anomaly_detection.ipynb
```

If the kernel is missing, register it with the `ipykernel install --prefix
machine-learning\.venv --name ecopulse-ml` command shown above.

---

## 7. What is not installed

The following are intentionally absent from the app bootstrap and will be added
with their phases:

- Apache Airflow
- PySpark and Java-based Spark jobs
- automated dataset download and a formal data-source manifest
- frontend end-to-end test tooling

The backend virtual environment does contain pandas, NumPy, scikit-learn,
Joblib and PyArrow: the API needs them to load and run the saved Phase 4
models, and they are pinned to the same versions the models were trained with.
Do not add Airflow, PySpark or the data-engineering pipeline code there.
Data-engineering and machine-learning pipeline packages live in their own
virtual environments, and Airflow will run in its own container.
