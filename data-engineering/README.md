# Data Engineering

Ingestion, validation, transformation, and exploratory analysis code lives here.
Phase 2 implements dataset inspection and EDA for the UCI Individual Household
Electric Power Consumption dataset. No cleaning, imputation, or production
pipeline is implemented yet.

## Boundaries

- `src/` - reusable scripts and modules for inspection, extraction, validation,
  and transformation.
- `notebooks/` - exploratory analysis only. Production logic must move into
  `src/` before it is considered part of the pipeline.
- `../reports/eda/` - generated inspection reports and EDA figures.
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

PySpark requires Java 17 and is not needed for Phase 2. To install only the EDA
toolchain:

```powershell
python -m pip install "pandas>=2.2,<3.0" "numpy>=1.26,<3.0" `
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

## Phase status

- Phase 1: monorepo, API, database, frontend, Compose, CI.
- Phase 2: raw dataset placed locally, inspection script, five reports, EDA
  notebook, ten figures, and documented findings.
- Phase 3 and later: ETL, PostgreSQL domain schema, Airflow/Spark pipelines,
  forecasting, anomaly detection, and analytics views.
