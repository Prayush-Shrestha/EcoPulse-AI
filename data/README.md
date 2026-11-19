# Data

This directory holds local datasets and derived files. No dataset files are
committed to Git.

## Directory contract

| Directory | Purpose | Committed |
| --- | --- | --- |
| `raw/` | Immutable downloads from the original source | No |
| `processed/` | Reproducible outputs derived from raw data | No |
| `external/` | Third-party reference data (for example holiday calendars) | No |

## Raw dataset

| Field | Value |
| --- | --- |
| Dataset | Individual Household Electric Power Consumption |
| Source | [UCI Machine Learning Repository, dataset 235](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption) |
| Local file | `raw/household_power_consumption.txt` |
| Licence | CC BY 4.0 |
| Rows | 2,075,259 |
| Columns | 9 |
| Time range | 2006-12-16 17:24:00 to 2010-11-26 21:02:00 |
| SHA-256 | `4259c9d7ece5dbee9ab8d53682baac68d791c864f0f64a52b4043cb3b90894b7` |
| Local file timestamp | 2026-11-18 |

The file is ignored by Git and must remain unchanged. Phase 2 inspection and EDA
are implemented in [`data-engineering/src/01_inspect_dataset.py`](../data-engineering/src/01_inspect_dataset.py)
and [`data-engineering/notebooks/01_exploratory_data_analysis.ipynb`](../data-engineering/notebooks/01_exploratory_data_analysis.ipynb).
Generated reports and figures live in [`reports/eda/`](../reports/eda/).

Download automation and a formal ingestion manifest remain future work; the
current file was placed manually for Phase 2 and is reused unchanged by Phases 3
and 4.

## Phase 3 processed datasets

Phase 3 reads the raw file without modifying it and writes four reproducible
Parquet datasets under `processed/`:

| File | Rows | Columns | Description |
| --- | ---: | ---: | --- |
| `household_power_cleaned.parquet` | 2,049,356 | 18 | Final minute-level modelling dataset with calendar and energy features |
| `household_power_hourly.parquet` | 34,589 | 20 | Gap-aware hourly aggregate |
| `household_power_daily.parquet` | 1,442 | 20 | Gap-aware daily aggregate |
| `household_power_monthly.parquet` | 48 | 20 | Gap-aware monthly aggregate |

The cleaned dataset excludes rows whose measurements could not be resolved. Only
gaps of at most five consecutive minutes were interpolated; longer gaps were not
zero-filled or fabricated. Aggregates retain expected, valid and imputed counts
so partial and empty intervals are explicit.

The workflow is implemented in
[`data-engineering/src/02_clean_dataset.py`](../data-engineering/src/02_clean_dataset.py),
[`03_transform_dataset.py`](../data-engineering/src/03_transform_dataset.py) and
[`04_run_etl_pipeline.py`](../data-engineering/src/04_run_etl_pipeline.py).
Reports and figures live in
[`reports/data-engineering/`](../reports/data-engineering/), and the executed
notebook is
[`02_data_cleaning_and_transformation.ipynb`](../data-engineering/notebooks/02_data_cleaning_and_transformation.ipynb).

## Phase 4 ML datasets

Phase 4 reads the Phase 3 Parquet files without modifying them and writes
reproducible machine-learning artefacts under `processed/ml/`:

| File | Description |
| --- | --- |
| `forecasting_dataset.parquet` | Hourly grid with causal features, target and chronological split labels |
| `forecasting_predictions.parquet` | Stored predictions for all five candidates and all splits |
| `preparation_summary.json` | Row counts, exclusions and split boundaries |
| `forecasting_training_summary.json` | Candidate parameters, validation ranking and selected model |
| `anomaly_dataset.parquet` | Cleaned minute rows with 20 model features and split labels |
| `anomaly_predictions.parquet` | Scores and flags for both unsupervised methods |
| `anomaly_training_summary.json` | Anomaly model parameters and split counts |

These files are ignored by Git. They are rebuilt by
`machine-learning/src/06_run_ml_pipeline.py`, which also writes six reports and
twelve figures under `reports/machine-learning/`. See the
[machine-learning README](../machine-learning/README.md) for the data contract.

## Rules

1. Keep raw files exactly as downloaded. Never hand-edit them.
2. Every processed file must be reproducible from a documented pipeline step.
3. Each ingested source needs a manifest entry with URL, retrieval date,
   licence/attribution, and checksum.
4. Do not commit datasets, database dumps, or generated plots.
5. Do not introduce synthetic "production" data to make a chart look complete.

## Candidate sources

Dataset selection is documented in [the architecture notes](../docs/architecture.md):

- [UCI: Individual household electric power consumption](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption)
- [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)
- [U.S. EIA Open Data](https://www.eia.gov/opendata/)
