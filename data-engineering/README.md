# Data Engineering

Ingestion, cleaning, validation, transformation and exploratory analysis code
lives here. Phases 2 and 3 implement the UCI Individual Household Electric Power
Consumption workflow: inspection and EDA (Phase 2), then deterministic cleaning,
feature engineering, gap-aware aggregation, validation and Parquet outputs
(Phase 3). No model training, forecasting, anomaly detection, dashboard work or
Phase 4 work is included.

## Boundaries

- `src/` - numbered production scripts for inspection, cleaning, transformation
  and ETL orchestration.
- `notebooks/` - executed analysis notebooks. Production logic stays in `src/`.
- `../reports/eda/` - Phase 2 inspection reports and EDA figures.
- `../reports/data-engineering/` - Phase 3 cleaning, transformation, validation
  and ETL reports, plus notebook figures.
- `../data/processed/` - generated Parquet datasets. They are ignored by Git and
  can be rebuilt from the immutable raw file.
- Airflow DAGs live in `../airflow/dags/`.
- Raw and processed data live in `../data/` and is never committed.

## Environment

This environment is deliberately separate from the FastAPI runtime:

```powershell
cd D:\ai\EcoPulse-AI\data-engineering
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PySpark requires Java 17 and is not needed for Phases 2-3. To install only the
inspection, cleaning, validation and notebook toolchain:

```powershell
python -m pip install "pandas>=2.2,<3.0" "numpy>=1.26,<3.0" `
  "pyarrow>=18,<27" "pandera>=0.24,<1.0" `
  "matplotlib>=3.9,<4.0" "seaborn>=0.13,<1.0" "notebook>=7.2,<8.0"
```

## Phase 2: inspect the dataset

The raw file must exist at `../data/raw/household_power_consumption.txt`. The
script resolves the repository root from its own location, so it can be run from
any directory:

```powershell
cd D:\ai\EcoPulse-AI
python data-engineering\src\01_inspect_dataset.py
```

It writes these files under `reports/eda/`:

- `dataset_inspection_report.txt`
- `missing_values_report.csv`
- `statistical_summary.csv`
- `duplicate_records_report.csv`
- `data_quality_report.txt`

The script does not modify the raw file. Missing `?` values are reported as NaN,
and no rows, missing values, or outliers are removed.

## Phase 2: run the EDA notebook

```powershell
cd D:\ai\EcoPulse-AI
data-engineering\.venv\Scripts\jupyter.exe notebook `
  data-engineering\notebooks\01_exploratory_data_analysis.ipynb
```

Run all cells from top to bottom. The notebook saves its ten figures to
`reports/eda/figures/` and embeds the executed outputs.

To execute it non-interactively and refresh the saved outputs:

```powershell
cd D:\ai\EcoPulse-AI\data-engineering\notebooks
..\.venv\Scripts\python.exe -m nbconvert --to notebook --execute --inplace `
  --ExecutePreprocessor.timeout=900 01_exploratory_data_analysis.ipynb
```

## Phase 3: clean and transform the dataset

The Phase 3 workflow is split into three numbered, path-independent scripts:

| Script | Responsibility |
| --- | --- |
| `src/02_clean_dataset.py` | Verify the raw checksum, parse timestamps, convert measurements, audit missing runs, interpolate short gaps and write the cleaned dataset |
| `src/03_transform_dataset.py` | Add calendar and energy features, build gap-aware hourly/daily/monthly aggregates and write four Parquet files |
| `src/04_run_etl_pipeline.py` | Run extract, clean, transform, load and validate in one command, then write validation and execution reports |

Run the complete pipeline from the repository root:

```powershell
cd D:\ai\EcoPulse-AI
data-engineering\.venv\Scripts\python.exe data-engineering\src\04_run_etl_pipeline.py
```

A successful run reports:

```text
Extract:   2,075,259 rows
Clean:     2,049,356 rows retained, 25,903 unresolved rows removed
Transform: 2,049,356 rows, 36,079 aggregate intervals
Load:      4 Parquet files
Validate:  90 passed, 0 failed, 6 warnings
```

The run takes under a minute locally. Every stage is deterministic for the same
raw file, and rerunning overwrites derived outputs safely.

### Cleaning policy

- The raw file is read-only and its SHA-256 checksum is verified before cleaning.
- `?` is mapped to `NaN`; no missing electricity reading is replaced with zero.
- Only internal gaps of one to five consecutive minutes are interpolated, using
  time-based linear interpolation on the all-seven-measurement rows.
- Longer gaps remain unresolved and are removed only from the final modelling
  dataset. Their row and cell counts are reported.
- IQR outliers and physical-domain anomalies are retained and documented.
  Genuine consumption peaks are not deleted or capped.
- Timestamps remain naive local civil time; no UTC offset or daylight-saving
  shift is invented.

### Output datasets

| File | Rows | Columns | Purpose |
| --- | ---: | ---: | --- |
| `data/processed/household_power_cleaned.parquet` | 2,049,356 | 18 | Final minute-level modelling dataset |
| `data/processed/household_power_hourly.parquet` | 34,589 | 20 | Gap-aware hourly aggregate |
| `data/processed/household_power_daily.parquet` | 1,442 | 20 | Gap-aware daily aggregate |
| `data/processed/household_power_monthly.parquet` | 48 | 20 | Gap-aware monthly aggregate |

Every aggregate includes `expected_observation_count`,
`valid_observation_count`, `imputed_observation_count`, `coverage_percentage`
and `is_complete`. Expected counts come from the complete one-minute grid, so
empty and partial intervals remain visible.

### Phase 3 reports

The pipeline writes these files under `reports/data-engineering/`:

- `cleaning_report.txt` - input integrity, missing-run analysis, interpolation,
  removal counts, outlier analysis and cleaning decisions.
- `missing_values_after_cleaning.csv` - per-column missing-value table for the
  final modelling dataset.
- `transformation_report.txt` - feature definitions, energy continuity and
  aggregation coverage.
- `data_validation_report.txt` - every passed check, failure and warning,
  including Pandera schemas and Parquet readback.
- `etl_execution_report.txt` - stage timings, record counts, output files,
  report inventory and final execution status.

## Phase 3: run the notebook

Run the ETL pipeline first so the four Parquet outputs exist. Then execute:

```powershell
cd D:\ai\EcoPulse-AI\data-engineering\notebooks
..\.venv\Scripts\python.exe -m nbconvert --to notebook --execute --inplace `
  --ExecutePreprocessor.timeout=1200 02_data_cleaning_and_transformation.ipynb
```

The notebook has 20 sections covering timestamp validation, missing values,
duplicate analysis, gap detection, short-gap interpolation, unresolved rows,
outliers, domain checks, schema verification, datetime features, energy,
hourly/daily/monthly aggregation, Pandera validation and findings. It saves ten
figures to `reports/data-engineering/figures/` and embeds the executed outputs.

## Phase status

- Phase 1: monorepo, API, database, frontend, Compose and CI.
- Phase 2: raw dataset inspection, five reports, EDA notebook and ten figures.
- Phase 3: cleaning, transformation, validation, ETL orchestration, four Parquet
  datasets, five reports and an executed 20-section notebook.
- Phase 4 and later: database ingestion, Airflow/Spark jobs, forecasting,
  anomaly detection and analytics views.
