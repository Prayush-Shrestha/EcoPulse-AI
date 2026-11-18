# Airflow

Airflow is part of the target architecture but is **not started in Phase 1**.
The `dags/` directory is intentionally empty.

## Windows constraint

Apache Airflow does not support running natively on Windows. It will run in its
own Linux container through Docker Compose in a later phase. Do not install
Airflow into the backend virtual environment.

## Planned integration

- DAGs in `dags/` call versioned Python modules from `../data-engineering/src/`.
- Airflow uses its own metadata database (a separate PostgreSQL database or
  schema), not the application's domain tables directly.
- Airflow version and providers will be pinned against the official constraints
  file for its Python version.
- The application stack must remain usable when Airflow is not running.

## Phase 1 status

No Airflow service, DAG, or dependency is included yet. The Compose foundation
covers PostgreSQL, FastAPI, and Next.js only.
