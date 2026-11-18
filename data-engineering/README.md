# Data Engineering

Ingestion, validation, and transformation code lives here. **Phase 1 contains
no pipeline implementation**; this is the prepared workspace for Phase 2.

## Boundaries

- `src/` - reusable modules for extraction, validation, and transformation.
- `notebooks/` - exploratory analysis only. Production logic must move into
  `src/` before it is considered part of the pipeline.
- Airflow DAGs live in `../airflow/dags/`.
- Raw and processed data lives in `../data/` and is never committed.

## Environment

This environment is deliberately separate from the FastAPI runtime. Install it
only when working on the data layer:

```powershell
cd D:\ai\EcoPulse-AI\data-engineering
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PySpark requires Java 17. Verify it with `java -version`. Local Windows file
access may require Hadoop `winutils.exe` and `HADOOP_HOME` for some Spark
operations; that will be documented and solved when the first pipeline needs it.

## Phase 1 status

- No dependencies installed as part of the app bootstrap.
- No datasets downloaded.
- No DAGs or Spark jobs written.
- Requirements are bounded to the analytics toolchain and are not installed in
  the backend virtual environment.
