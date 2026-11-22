# EcoPulse AI backend

FastAPI service that stores the real Phase 3 dataset in PostgreSQL and serves
real Phase 4 model inference: energy queries, recursive forecasts, anomaly
scoring, analytics and model metadata.

Everything in this document was executed locally on Windows 11. Numbers below
are measured, not estimated.

---

## 1. What the API does

| Group | Endpoints | Behaviour |
| --- | --- | --- |
| Health | `GET /api/v1/health`, `/health/live`, `/health/ready` | API, PostgreSQL and saved-model status |
| Energy | `GET /api/v1/energy`, `/energy/summary`, `/energy/hourly`, `/energy/daily`, `/energy/monthly` | Stored minute readings and aggregates |
| Forecasts | `POST /api/v1/forecasts/predict`, `GET /forecasts/history`, `GET /forecasts/latest` | Recursive hourly forecasts, persisted |
| Anomalies | `POST /api/v1/anomalies/detect`, `GET /anomalies`, `GET /anomalies/summary` | Isolation Forest scoring, persisted |
| Analytics | `GET /api/v1/analytics/overview`, `/analytics/consumption-patterns` | Aggregates over stored data only |
| Models | `GET /api/v1/models`, `/models/{model_key}` | Loaded artefact metadata and thresholds |

Interactive documentation: `/docs` (Swagger UI), `/redoc` (ReDoc),
`/openapi.json` (machine-readable spec).

The full endpoint reference, request parameters and response fields are in the
generated docs; this file documents setup, guarantees and verification.

---

## 2. Prerequisites

- Python 3.11-3.13 (3.13.4 used locally)
- PostgreSQL 17 (the Compose `db` container is enough)
- Phase 3 output `data/processed/household_power_cleaned.parquet`
- Phase 4 artefacts under `machine-learning/models/`

The backend virtual environment intentionally contains the inference stack
(`pandas`, `numpy`, `scikit-learn`, `joblib`, `pyarrow`) pinned to the same
versions the models were trained with. It does **not** import
`machine-learning/` or `data-engineering/` code at runtime; inference features
are reimplemented in `app/ml/inference.py` and verified against Phase 4 outputs.

---

## 3. Setup (Windows)

```powershell
cd D:\ai\EcoPulse-AI
docker compose up -d db            # start Docker Desktop first

cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env        # then edit DATABASE_URL if needed
alembic upgrade head
```

> **Port note.** `docker-compose.yml` publishes PostgreSQL on host port `5433`
> so it does not collide with other local databases. A native `backend/.env`
> must therefore use `localhost:5433`. The Compose backend uses `db:5432`
> inside the network.

`.env` is Git-ignored. Never commit credentials.

### Environment variables

| Variable | Purpose | Example |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy URL (Psycopg 3 driver only) | `postgresql+psycopg://ecopulse:ecopulse_local_dev@localhost:5433/ecopulse` |
| `ML_MODELS_DIR` | Directory holding the saved Phase 4 artefacts | `../machine-learning/models` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins | `http://localhost:3000` |
| `ENVIRONMENT` | `development`, `test`, `production` | `development` |
| `DEBUG` | Adds exception type to 500 responses (never a traceback) | `false` |
| `LOG_LEVEL` | Structured JSON log level | `INFO` |
| `IMPORT_BATCH_SIZE` | Rows per import batch (max 6000) | `5000` |
| `IMPORT_PROGRESS_EVERY` | Batches between progress lines | `10` |

Relative paths resolve from `backend/`.

---

## 4. Database and migrations

| Revision | Contents |
| --- | --- |
| `0001` | Empty Phase 1 baseline (migration history only) |
| `0002` | `energy_readings`, `forecast_records`, `anomaly_records` |

```powershell
alembic upgrade head       # apply
alembic current            # expect: 0002 (head)
alembic downgrade 0001     # reversible
```

Schema decisions:

- Measurement, forecast and score columns use `Numeric(18, 9)` so that hourly
  sums of minute values keep their precision (minute energy values are
  recurring decimals such as `0.070266666666667`).
- `energy_readings.timestamp` is unique and naive (local civil time), matching
  the immutable Phase 3 dataset. Timezone-aware values are rejected at the API
  boundary.
- Audit columns (`created_at`, `detected_at`) are timezone-aware server times.

---

## 5. Importing the dataset

```powershell
python scripts\import_processed_data.py --dry-run          # validate, no writes
python scripts\import_processed_data.py --limit 1000       # smoke import
python scripts\import_processed_data.py                    # full import
```

The script streams Parquet row groups (the file is never fully materialised),
validates schema, nulls, numeric ranges and timestamp naivety, and inserts with
`ON CONFLICT (timestamp) DO NOTHING` so re-runs are idempotent. `RETURNING id`
reports exactly how many rows were inserted rather than skipped.

Verified full run:

```text
Rows in Parquet file: 2,049,356
Inserted             : 2,029,356     (20,000 already present)
Rows after           : 2,049,356
Elapsed              : 736.91 s      (~2,781 source rows/s)
```

Verified idempotency run immediately afterwards:

```text
Inserted             : 0
Skipped / duplicates : 2,049,356
Rows before / after  : 2,049,356 / 2,049,356
```

Useful flags: `--batch-size`, `--limit`, `--start`, `--end`, `--progress-every`,
`--dry-run`.

---

## 6. Running the service

```powershell
cd D:\ai\EcoPulse-AI\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Startup order: configure logging → database `SELECT 1` health check → load both
model artefacts once (thread-safe, process-wide registry) → serve. Missing model
files never crash startup; they are reported as `degraded` by `/api/v1/health`
and as `503 model_unavailable` on inference routes.

---

## 7. Inference guarantees

- **Real models only.** The saved Phase 4 `Random Forest` (forecasting) and
  `Isolation Forest` (anomaly) bundles are loaded from `machine-learning/models`.
- **Exact feature parity.** Reimplemented features were compared against the
  Phase 4 datasets on real rows: forecast features differed by at most
  `4.219e-15` and predictions by `3.331e-16`; anomaly features differed by at
  most `5.955e-12`, scores by `6.801e-09`, with zero label disagreements,
  including rows the model flags as anomalies.
- **No future leakage.** Forecasts are recursive: each step uses observed
  history plus earlier predictions, and values at or after the target timestamp
  are excluded by construction. Anomaly rolling statistics are shifted by one
  minute so a reading is never part of its own baseline.
- **Supported horizons:** 1, 6, 24 and 48 hours (recursive multi-step).
- **Anomaly threshold:** `decision_function < 0.0` marks a deviation. The bundle
  also stores scikit-learn's raw `score_samples` offset (`-0.6677766878861168`),
  exposed as `raw_offset` so the two are never confused.
- **Honesty constraints.** Anomaly severity (`none/low/medium/high`) is a
  documented heuristic for triage, not a calibrated fault severity. No labelled
  accuracy, precision, recall or F1 is claimed anywhere in the API.
- **Missing artefacts** produce an explicit `503 model_unavailable` error with a
  safe reason, never a fabricated prediction.

---

## 8. Error contract

Every failure uses one JSON envelope:

```json
{ "error": { "code": "validation_error", "message": "...", "details": null } }
```

| Status | Code | Example cause |
| --- | --- | --- |
| `404` | `not_found` | Unknown route, unknown model key, missing observation |
| `422` | `validation_error` | Invalid horizon, reversed range, timezone-aware timestamp |
| `422` | `insufficient_history` | Fewer than 24 prior observed hours |
| `503` | `database_unavailable` | PostgreSQL unreachable |
| `503` | `model_unavailable` | Joblib artefact missing or unreadable |
| `500` | `internal_error` | Unexpected failure; traceback never returned |

Responses carry an `X-Request-ID` header (generated when absent) that is also
written to the structured JSON logs.

---

## 9. Tests

```powershell
cd D:\ai\EcoPulse-AI\backend
ruff check .
pytest          # add -v for the per-test view
```

- Tests use a **dedicated** `ecopulse_test` database derived from
  `DATABASE_URL` (or `TEST_DATABASE_URL`). The development database is never
  touched by the suite.
- The schema is recreated from SQLAlchemy metadata and seeded with a real
  17,103-row Phase 3 slice (`2010-11-15T00:00:00` … `2010-11-26T21:02:00`).
- Each test runs inside an outer transaction that is rolled back, so writes do
  not leak between tests.
- `data/processed/` and the Joblib binaries are Git-ignored, so a fresh clone
  skips the tests that need them with an explicit reason instead of failing or
  inventing substitute data:

```text
SKIPPED ... The Phase 4 Joblib artefacts are missing under machine-learning/models.
SKIPPED ... data/processed/household_power_cleaned.parquet is missing.
```

Verified locally with all artefacts present: **55 passed**. Simulated fresh
clone without models: **28 passed, 27 skipped**. Without the Parquet seed:
**12 passed, 43 skipped**. All runs exit `0`; `ruff check .` is clean.

---

## 10. Live endpoint verification

A real Uvicorn process was started against the fully imported development
database and exercised end to end (34 checks, 0 failures), including:

| Check | Result |
| --- | --- |
| `/`, `/docs`, `/redoc`, `/openapi.json` | `200`, all 16 documented paths present |
| `/api/v1/health` (+ `/live`, `/ready`) | `ok`, database and both models loaded |
| `/api/v1/energy` | `total = 2,049,356`, first row `2006-12-16T17:24:00` |
| `/api/v1/energy/summary` | `2,049,356` observations, `37,286.170549375` kWh |
| `POST /forecasts/predict` base `2010-11-26T19:00:00` | `1.897491782047391` kWh for target `20:00` (Phase 4 stored `1.897491782047`) |
| `POST /forecasts/predict` 6 h / 48 h | 6 and 48 ordered recursive points |
| `GET /forecasts/history?forecast_horizon=1&model_name=Random Forest` | `200` with filtered totals |
| `POST /anomalies/detect` `2010-11-26T21:01:00` | score `0.222983398`, not anomalous (Phase 4 `0.222983405`) |
| `POST /anomalies/detect` `2010-11-20T19:05:00` | score `-0.018904201`, flagged (Phase 4 `-0.018904202`) |
| `GET /analytics/overview` | energy `2,049,356`, 55 forecast points, 6 detections |
| `GET /models/anomaly_detection` | `threshold 0.0`, `raw_offset -0.6677766878861168` |
| 404 / 422 / 404-observation cases | correct error envelopes, no stack traces |

Also verified: DB-derived hourly history matches the Parquet-derived series
used by Phase 4 to within `6.4e-9` per hour over a 200-hour window (the residual
is `Numeric(18, 9)` storage rounding).

---

## 11. Project layout

```text
backend/
├── alembic/                  Migration environment
│   └── versions/             0001 baseline, 0002 domain tables
├── app/
│   ├── api/v1/endpoints/     health, energy, forecasts, anomalies, analytics, models
│   ├── api/v1/router.py      Versioned router mounted at /api/v1
│   ├── core/                 Settings, typed errors, JSON logging
│   ├── db/                   Engine, session, declarative base
│   ├── ml/                   Model registry and causal inference features
│   ├── models/               SQLAlchemy ORM models
│   ├── repositories/         Query layer
│   ├── schemas/              Pydantic request/response contracts
│   ├── services/             Business logic
│   └── main.py               Lifespan, middleware, error handlers, docs
├── scripts/
│   └── import_processed_data.py   Batched idempotent Parquet importer
├── tests/                    55 tests against ecopulse_test
├── requirements.txt          Runtime, pinned to Phase 4 versions
└── requirements-dev.txt      Test and lint tooling
```

---

## 12. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `connection timeout expired ... port 5433` | Docker Desktop stopped. Start it, wait for the engine, confirm `docker compose ps` shows `db` healthy. |
| `DATABASE_URL must use the postgresql+psycopg:// driver` | Use the Psycopg 3 URL format shown above. |
| `model_unavailable` on predict | Run the Phase 4 pipeline, or point `ML_MODELS_DIR` at `machine-learning/models`. |
| `insufficient_history` on detect | Score a timestamp with at least 24 prior observed hours; interpolated minutes are excluded from history. |
| Tests skip with a reason | Run Phase 3 / Phase 4 to regenerate the Git-ignored artefacts. |
| `alembic` says `0001 (head)` | Run `alembic upgrade head` to apply revision `0002`. |
| PowerShell blocks venv activation | `Set-ExecutionPolicy -Scope Process Bypass` then activate, or call `.venv\Scripts\python.exe` directly. |
