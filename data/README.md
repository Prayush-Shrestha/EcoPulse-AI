# Data

This directory holds local datasets and derived files. No dataset files are
committed to Git.

## Directory contract

| Directory | Purpose | Committed |
| --- | --- | --- |
| `raw/` | Immutable downloads from the original source | No |
| `processed/` | Reproducible outputs derived from raw data | No |
| `external/` | Third-party reference data (for example holiday calendars) | No |

## Phase 2 dataset

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
current file was placed manually for Phase 2.

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
