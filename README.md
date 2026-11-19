# EcoPulse AI

**Intelligent energy consumption monitoring, forecasting and anomaly detection.**

A local-first data and analytics platform built as a solo portfolio project. It
combines data engineering, machine learning, and full-stack development on a
fully inspectable local stack: no cloud hosting, no paid services, and no
invented production data.

> **Project status: Phase 4 - Intelligence: forecasting and anomaly detection.**
> The monorepo, interface, API health contract, database wiring, containers, CI,
> raw dataset, inspection reports, EDA, and the Phase 3 cleaning and
> transformation ETL are in place. Phase 4 adds a reproducible, leakage-safe
> hourly forecasting experiment, an unsupervised anomaly-detection experiment,
> six machine-learning reports, twelve real figures, locally saved models, and
> two executed notebooks. API serving, analytics dashboards, and cloud
> deployment are deliberately not implemented yet.

---

## What this is

EcoPulse AI is being built to answer three practical questions from real energy
data:

1. **What is consuming energy?** - interval-level monitoring with transparent
   data-quality treatment.
2. **What happens next?** - consumption forecasts evaluated with chronological
   splits and documented error metrics.
3. **What changed?** - anomaly detection that explains deviations in context.

The project is designed as a complete path from public dataset to local
analytics interface. Every layer is documented so the system can be understood,
run, and verified by another developer.

### What is intentionally absent

- No synthetic production data, sample dashboards, or placeholders that look
  like real measurements.
- No fabricated model metrics or anomaly labels. Phase 4 results are computed
  from the real Phase 3 Parquet outputs, and anomaly detections are explicitly
  unlabelled deviation candidates.
- No cloud infrastructure, paid APIs, or live deployment.
- No authentication or multi-user tenancy; this is a local single-user project.
- No Airflow or Spark runtime in Phase 3. They are documented in the target
  architecture and will be added with the orchestration phase.

---

## Stack

| Layer | Technology | Role |
| --- | --- | --- |
| Interface | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Recharts | Product surface and future analytics views |
| API | Python, FastAPI, Pydantic, SQLAlchemy 2 | Typed local service and health contract |
| Database | PostgreSQL 17, Alembic | Durable storage and versioned schema |
| Data engineering | Pandas, NumPy, PyArrow, Pandera, PySpark, Apache Airflow | Cleaning, validation, transformation and orchestration |
| Machine learning | scikit-learn, Joblib | Hourly forecasting and unsupervised anomaly detection (Phase 4) |
| Testing | Pytest, Ruff, ESLint, TypeScript | Backend tests and frontend quality gates |
| Infrastructure | Docker, Docker Compose, GitHub Actions | Reproducible local runtime and CI |

Python environments are intentionally separated:

- `backend/` runs the API only.
- `data-engineering/` and `machine-learning/` carry the heavier analytics stack.
- Airflow will run in its own container, not in the API virtual environment.

---

## Architecture

The target data path is documented in [docs/architecture.md](docs/architecture.md).

```mermaid
flowchart LR
    A[Public datasets] --> B[Apache Airflow]
    B --> C[Pandas / PySpark]
    C --> D[(PostgreSQL)]
    D --> E[scikit-learn / Joblib]
    D --> F[FastAPI]
    E --> F
    F --> G[Next.js / Recharts]
```

Implemented in Phase 1:

- Next.js interface with a live infrastructure-status panel
- FastAPI service with liveness, readiness, and aggregate health endpoints
- SQLAlchemy session layer and an Alembic baseline migration
- PostgreSQL and application images wired through Docker Compose
- CI for backend lint/tests, frontend lint/types/build, and Compose validation

Phase 2 adds:

- UCI Individual Household Electric Power Consumption dataset pinned in `data/raw/`
- Dataset inspection script and five generated reports in `reports/eda/`
- Executed EDA notebook with ten saved figures (`reports/eda/figures/`)

Phase 3 adds:

- Cleaning and transformation modules with a narrow five-minute interpolation
  rule and explicit unresolved-gap accounting
- Four Parquet datasets in `data/processed/`: minute, hourly, daily and monthly
- Five reports in `reports/data-engineering/` and ten notebook figures
- Pandera schemas, cross-aggregate checks and Parquet readback validation
- An executed 20-section cleaning and transformation notebook

Phase 4 adds:

- Phase 3 Parquet inputs that are validated before any training or scoring
- A chronological 70/15/15 hourly forecasting experiment with five candidates,
  validation-only model selection, and a one-time test evaluation
- A leakage-safe 24-feature pipeline and a saved Random Forest bundle that
  reproduces its stored test predictions
- A train-only Isolation Forest plus a causal rolling z-score baseline, with no
  supervised accuracy claims
- Six reports and twelve figures in `reports/machine-learning/`
- Two executed notebooks covering forecasting and anomaly detection

Still not implemented: automated dataset download, domain ingestion into
PostgreSQL, domain schema models, Airflow DAGs, Spark jobs, API serving of
forecasts or anomaly scores, and energy dashboards.

---

## Repository layout

```text
EcoPulse-AI/
├── .github/workflows/ci.yml    CI: backend, frontend, Compose validation
├── .env.example                Docker Compose environment
├── airflow/
│   └── dags/                   Airflow DAGs (later phases)
├── backend/
│   ├── alembic/                Migration environment and baseline revision
│   ├── app/
│   │   ├── api/v1/             Versioned HTTP routes
│   │   ├── core/               Settings
│   │   ├── db/                 SQLAlchemy engine, session, declarative base
│   │   ├── models/             ORM models (empty until domain ingestion)
│   │   ├── schemas/            Pydantic response models
│   │   └── main.py             FastAPI application factory
│   ├── tests/                  Pytest health-contract tests
│   ├── Dockerfile
│   └── requirements*.txt
├── data/
│   ├── raw/                    Immutable downloads (ignored by Git)
│   ├── processed/              Derived datasets (ignored by Git)
│   └── external/               Third-party reference data (ignored by Git)
├── data-engineering/
│   ├── src/                    Inspection, cleaning, transformation and ETL modules
│   ├── notebooks/              Executed Phase 2-4 notebooks
│   └── requirements.txt
├── database/
│   ├── init/                   Future bootstrap SQL
│   └── seeds/                  Small documented reference data
├── docs/
│   ├── architecture.md
│   ├── design-system.md
│   └── development.md
├── frontend/
│   ├── app/                    App Router pages, layout, global styles
│   ├── components/             Product surface and live status components
│   ├── lib/                    Site configuration and health client
│   ├── Dockerfile
│   └── package.json
├── machine-learning/
│   ├── src/                    Phase 4 preparation, training and evaluation scripts
│   ├── utils/                  Shared features, metrics and validation
│   ├── models/                 Local Joblib artefacts; JSON metadata is committed
│   └── requirements.txt
├── reports/
│   ├── eda/                    Phase 2 inspection reports and figures
│   ├── data-engineering/       Phase 3 cleaning, validation and ETL reports
│   └── machine-learning/       Phase 4 metrics, reports and twelve figures
├── scripts/                    Reserved for repeatable operations
├── tests/                      Future cross-system tests
└── docker-compose.yml
```

---

## Quick start

### Prerequisites

- Windows 11
- Node.js 22+ and npm
- Python 3.11-3.13 (3.13 tested locally; containers use 3.12)
- Docker Desktop with the WSL 2 backend
- Git

Java 17 is only needed for future PySpark work; Airflow will run in Docker
because it does not support native Windows execution.

### Option A - full stack with Docker Compose

```powershell
cd D:\ai\EcoPulse-AI
Copy-Item .env.example .env
# Start Docker Desktop first, then:
docker compose up --build
```

| Service | URL |
| --- | --- |
| Web interface | http://localhost:3000 |
| FastAPI docs | http://localhost:8000/docs |
| Aggregate health | http://localhost:8000/api/v1/health |
| PostgreSQL | localhost:5432 |

Stop the stack with `docker compose down`. Add `-v` only when you intentionally
want to delete the local database volume.

### Option B - local development

Start PostgreSQL only:

```powershell
cd D:\ai\EcoPulse-AI
docker compose up -d db
```

Backend (terminal 1):

```powershell
cd D:\ai\EcoPulse-AI\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (terminal 2):

```powershell
cd D:\ai\EcoPulse-AI\frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The status panel queries the real API health
endpoint; when PostgreSQL is unavailable it reports a degraded state instead of
inventing a successful one.

### Option C - Phase 4 machine-learning pipeline

The four Phase 3 Parquet outputs must exist in `data/processed/`. Use the
dedicated ML environment; do not install these packages into the backend:

```powershell
cd D:\ai\EcoPulse-AI\machine-learning
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd D:\ai\EcoPulse-AI
machine-learning\.venv\Scripts\python.exe machine-learning\src\06_run_ml_pipeline.py
```

The pipeline validates the Phase 3 inputs, prepares both leakage-safe datasets,
trains and evaluates five forecasting candidates, fits the unsupervised anomaly
detectors, reloads both saved models, and writes six reports plus twelve figures.
The verified local run completed in about 163 seconds with 128/128 checks passed.
See [machine-learning/README.md](machine-learning/README.md) for the data
contract, results and notebook commands.

---

## Environment variables

| Variable | Used by | Default / example | Purpose |
| --- | --- | --- | --- |
| `POSTGRES_DB` | Compose | `ecopulse` | Database name |
| `POSTGRES_USER` | Compose | `ecopulse` | Database role |
| `POSTGRES_PASSWORD` | Compose | `ecopulse_local_dev` | Local-only password |
| `POSTGRES_PORT` | Compose | `5432` | Host port for PostgreSQL |
| `API_PORT` | Compose | `8000` | Host port for FastAPI |
| `FRONTEND_PORT` | Compose | `3000` | Host port for Next.js |
| `DATABASE_URL` | Backend | `postgresql+psycopg://...` | SQLAlchemy connection URL |
| `CORS_ORIGINS` | Backend | `http://localhost:3000,...` | Comma-separated browser origins |
| `ENVIRONMENT` | Backend | `development` | `development`, `test`, or `production` |
| `DEBUG` | Backend | `false` | Debug flag |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://localhost:8000` | Browser-accessible API base URL |

Copy the provided `.env.example` files. Never commit `.env` files. Docker
Compose uses the root `.env`; native backend and frontend development use their
own local files.

---

## Quality checks

```powershell
# Backend
cd D:\ai\EcoPulse-AI\backend
.\.venv\Scripts\Activate.ps1
ruff check .
pytest

# Frontend
cd D:\ai\EcoPulse-AI\frontend
npm run lint
npm run typecheck
npm run build

# Compose configuration
cd D:\ai\EcoPulse-AI
docker compose --env-file .env.example config --quiet

# Phase 4 machine-learning pipeline and artefact verification
machine-learning\.venv\Scripts\python.exe machine-learning\src\06_run_ml_pipeline.py
```

GitHub Actions runs the same quality gates, including migrations against a real
PostgreSQL service. Container images are not yet built in CI; Compose syntax is
validated there and local builds are documented in
[docs/development.md](docs/development.md).

### API endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| `GET` | `/` | Service metadata |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/api/v1/health` | Aggregate health; always `200`, may be `degraded` |
| `GET` | `/api/v1/health/live` | API liveness; no database access |
| `GET` | `/api/v1/health/ready` | Readiness; `503` when a dependency is unavailable |

---

## Data principles

The project uses real public datasets only. Phase 2 selects the UCI household
dataset, records its source, licence and SHA-256 checksum, and profiles it before
any data is ingested. Phase 3 cleans and transforms it with documented rules:
only short gaps are interpolated, long gaps are not zero-filled, and unresolved
rows are excluded only from the final modelling dataset. Phase 4 reads those
Parquet files directly, validates them again, and preserves the same rules when
building features. Automated retrieval and the formal manifest are future work.

- Raw data stays immutable in `data/raw/`.
- Processed data is reproducible, never hand-edited.
- No chart is populated with invented values.
- Model quality is reported against a baseline with chronological evaluation.
- Unsupervised detections are labelled as candidates, never as confirmed faults.

See [data/README.md](data/README.md) and
[docs/architecture.md](docs/architecture.md#data-principles).

---

## Design direction

The interface uses a premium energy-intelligence identity: deep green-black
surfaces, restrained signal green, Geist typography, fine hairlines, and a
compact instrument-panel hierarchy.

### Palette

| Token | Hex | Usage |
| --- | --- | --- |
| Canvas | `#101713` | Page background |
| Surface | `#171F19` | Panels and cards |
| Surface raised | `#202A22` | Hover / secondary surfaces |
| Primary green | `#8BCF9B` | Signal, focus, primary actions |
| Accent green | `#B6E3B7` | Hover and emphasis |
| Primary text | `#F1F5F1` | Headings and body |
| Secondary text | `#9BA99D` | Supporting copy and metadata |

Full tokens and usage rules are in
[docs/design-system.md](docs/design-system.md).

---

## Documentation

- [Architecture](docs/architecture.md) - boundaries, runtime topology, decisions
- [Development](docs/development.md) - verified versions, setup, troubleshooting
- [Design system](docs/design-system.md) - visual identity and chart guidance
- [Data engineering](data-engineering/README.md) - inspection, cleaning, ETL and notebooks
- [Machine learning](machine-learning/README.md) - Phase 4 forecasting, anomaly detection and verification
- [Data directory](data/README.md) - dataset rules and directory contract
- [Database](database/README.md) - schema ownership and migration workflow

---

## Known limitations

- Phases 1-4 only: no domain ingestion into PostgreSQL, no API serving of
  forecasts or anomaly scores, and no live energy charts. Raw data, processed
  Parquet files, model binaries, reports and figures are local files.
- Forecasting is one household and one chronological hold-out. It is not a
  cross-household generalisation claim, and recursive multi-day forecasting was
  not evaluated.
- The anomaly experiment has no reliable labels, so accuracy, precision, recall
  and F1 are not reported. Flagged minutes are statistical deviations for
  investigation, not confirmed faults.
- Airflow is not running natively or in Compose yet; it is container-only on
  Windows and will arrive with the orchestration phase.
- The processed datasets exclude unresolved long gaps; aggregate totals for
  partial intervals therefore cover valid minutes only and are flagged.
- The Docker images have not been exercised automatically in CI.
- There is no authentication because the system is designed for local use only.
- The frontend status panel shows infrastructure state only. It is deliberately
  not a metrics dashboard.

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 01 | Foundation: monorepo, UI shell, API, database wiring, containers, CI | Complete |
| 02 | Dataset collection, inspection, EDA, reports and findings | Complete |
| 03 | Cleaning, transformation, validation, ETL and Parquet outputs | Complete |
| 04 | Intelligence: hourly forecasting, anomaly detection and evaluation | Complete |
| 05 | Experience: real-data dashboards, integration and end-to-end tests | Not started |

Phases 1-4 are complete. Phase 5 remains intentionally unimplemented.
