# Machine Learning

Phase 4 implements the local-only intelligence layer for EcoPulse AI: hourly
energy forecasting and unsupervised anomaly detection. Both workflows read the
real Phase 3 Parquet outputs, use chronological splits, persist their fitted
artefacts locally, and write evidence reports and figures.

**Status:** Phase 4 is complete. No Phase 5 dashboard, API serving, cloud model
registry, or labelled anomaly claim is included.

## Environment

Use a dedicated environment; do not install these packages into the backend:

```powershell
cd <repo>\machine-learning
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verified locally: Python 3.13.4, scikit-learn 1.9.1, pandas 2.3.3, NumPy 2.5.5,
PyArrow 26.0.1, matplotlib 3.11.2, seaborn 0.13.2 and Joblib 1.6.0.

## One-command pipeline

Prerequisite: the four Phase 3 Parquet datasets already exist in
`data/processed/`.

```powershell
cd <repo>
machine-learning\.venv\Scripts\python.exe machine-learning\src\06_run_ml_pipeline.py
```

The pipeline runs input validation, data preparation, both training stages, both
evaluation stages and a final reload/leakage verification. A successful run ends
with `PHASE 4 PIPELINE STATUS: PASSED` and writes
`reports/machine-learning/model_evaluation_report.txt`. The verified run on this
machine completed in about 163 seconds and passed 128 checks with no warnings.

## Data contract

| Item | Forecasting | Anomaly detection |
| --- | --- | --- |
| Source | `household_power_hourly.parquet` | `household_power_cleaned.parquet` |
| Prepared output | `data/processed/ml/forecasting_dataset.parquet` | `data/processed/ml/anomaly_dataset.parquet` |
| Supervised rows | 31,451 complete clock-hours | not applicable |
| Usable observations | 31,451 hourly rows | 2,043,373 minute rows |
| Train / validation / test | 22,015 / 4,717 / 4,719 | 1,430,361 / 306,505 / 306,507 |
| Split policy | chronological 70/15/15, no shuffle | chronological 70/15/15, no shuffle |

Prepared datasets, predictions and training summaries live under
`data/processed/ml/` and are ignored by Git because they are reproducible from
the committed code and Phase 3 inputs.

## Forecasting

**Target:** `total_energy_consumption_kwh` for a complete clock-hour, defined as
exactly 60 valid one-minute observations. Incomplete and boundary hours keep a
missing target and are never converted to zero. The 31,451 modelling rows cover
0.1240-6.5605 kWh (mean 1.0932, median 0.8043).

**Features:** 24 causal features.

- Calendar: hour, day of week, day of month, day of year, week of year, month,
  weekend flag.
- Cyclical: sine/cosine encodings for hour, weekday and month.
- Lags: 1, 2, 3, 24, 48 and 168 hours.
- Rolling: means over 3, 6, 24 and 168 hours, plus the 24-hour standard
  deviation.

Every lag and rolling statistic is shifted by one hour, so the current and future
target cannot enter its own features. Feature warm-up is excluded before the
split is assigned.

**Candidates:** lag-1 persistence, 24-hour seasonal persistence, Linear
Regression (with train-only standardisation), Random Forest and
HistGradientBoosting. Hyperparameters are fixed a priori with random seed 42.

**Selection:** validation RMSE only. The test split is predicted once after
selection and is not used to re-rank models.

| Model | Validation RMSE | Validation MAE |
| --- | ---: | ---: |
| Random Forest | 0.5390 | 0.3736 |
| HistGradientBoosting | 0.5453 | 0.3776 |
| Linear Regression | 0.5854 | 0.4207 |
| Naive (lag 1) | 0.6927 | 0.4659 |
| Seasonal Naive (lag 24) | 0.9672 | 0.6723 |

The selected Random Forest achieved test MAE 0.3194 kWh, RMSE 0.4626 kWh, R2
0.5726, MAPE 43.73% and sMAPE 34.16%. MAPE is reported only because every
evaluated complete-hour target is non-zero; sMAPE is included because MAPE is
unstable near zero.

## Anomaly detection

The cleaned minute dataset contains 2,049,356 rows. The anomaly workflow excludes
the 76 interpolated rows and 5,983 rows without a complete prior 24-hour
baseline, leaving 2,043,373 scored minutes.

**Features:** 20 multivariate features covering the seven power measurements,
calendar context (hour, weekday, weekend and cyclical encodings) and historical
active-power statistics. All rolling statistics are shifted by one minute.

**Method A - causal rolling z-score:** `|z| >= 3.0`, where the mean and standard
deviation come from the previous 24 hours of `Global_active_power` after a
one-minute shift.

**Method B - Isolation Forest:** 200 trees, `max_samples=256`,
`contamination=0.005`, `random_state=42`. The StandardScaler and forest are fitted
on the training split only. The decision threshold is `0.0`; the stored raw-score
`offset_` is -0.667777.

| Method | Flagged minutes | Overall rate |
| --- | ---: | ---: |
| Rolling z-score | 45,325 | 2.218% |
| Isolation Forest | 8,809 | 0.431% |

The methods agree on 6,291 minutes (Jaccard 13.15%). The Isolation Forest
in-sample training rate is 0.500%, validation 0.420% and test 0.121%; these rates
are descriptive, not accuracy.

**No reliable anomaly labels exist.** Accuracy, precision, recall and F1 are
deliberately not reported. A flagged minute is a statistical deviation candidate
for investigation, not a confirmed fault.

## Stage scripts

| Script | Responsibility |
| --- | --- |
| `src/01_prepare_ml_data.py` | Validate Phase 3 inputs, build both leakage-safe datasets, run 71 checks and save them |
| `src/02_train_forecasting_models.py` | Fit the five candidates, select on validation RMSE and persist only the selected model |
| `src/03_evaluate_forecasting_models.py` | Recompute metrics, verify the saved model, write three reports and six figures |
| `src/04_train_anomaly_detection.py` | Fit the train-only scaler/Isolation Forest, score all splits and save predictions and metadata |
| `src/05_evaluate_anomaly_detection.py` | Reconcile counts, compute agreement, verify reloaded flags, write two reports and six figures |
| `src/06_run_ml_pipeline.py` | Run all stages, reload both models, verify causality/splits/artefacts and write the sixth report |

Shared code lives in:

- `utils/features.py` - dataset builders, constants, split assignment and
  `LagBaseline`.
- `utils/metrics.py` - MAE, RMSE, R2, MAPE validity handling and sMAPE.
- `utils/validation.py` - Phase 3 input checks, split/leakage checks and saved
  model reload verification.

## Reports and artefacts

The six required reports are in `reports/machine-learning/`:

1. `forecasting_metrics.csv` - metrics for every model and split.
2. `forecasting_comparison.csv` - validation ranking with one-time test results.
3. `forecasting_report.txt` - full forecasting methodology and findings.
4. `anomaly_summary.csv` - detection counts overall and by split.
5. `anomaly_detection_report.txt` - methods, agreement, extreme observations and
   limitations.
6. `model_evaluation_report.txt` - stage timing, prepared-data counts, final
   results, artefact inventory and every verification check.

Twelve real figures live in `reports/machine-learning/figures/`: six forecasting
and six anomaly plots generated from the saved predictions.

Model binaries are local and ignored by Git:

- `models/forecasting/best_forecasting_model.joblib`
- `models/anomaly_detection/isolation_forest.joblib`
- `models/anomaly_detection/anomaly_scaler.joblib`

Small metadata and feature definitions are committed alongside them:
`forecasting_metadata.json`, `forecasting_features.json`, `anomaly_metadata.json`
and `anomaly_features.json`.

## Notebooks

The executed Phase 4 notebooks are stored with the other project notebooks:

- `data-engineering/notebooks/03_energy_forecasting.ipynb`
- `data-engineering/notebooks/04_anomaly_detection.ipynb`

They load the saved datasets, predictions, summaries and model bundles; recompute
the verification metrics and flags; display the embedded figures; and contain no
hard-coded result values.

Register the ML kernel once, then execute a notebook:

```powershell
cd <repo>
machine-learning\.venv\Scripts\python.exe -m ipykernel install `
  --prefix machine-learning\.venv --name ecopulse-ml `
  --display-name "EcoPulse ML (Python 3.13)"

$env:JUPYTER_PATH = "$PWD\machine-learning\.venv\share\jupyter"
machine-learning\.venv\Scripts\python.exe -m nbconvert --to notebook --execute `
  --inplace --ExecutePreprocessor.timeout=900 `
  --ExecutePreprocessor.kernel_name=ecopulse-ml `
  data-engineering\notebooks\03_energy_forecasting.ipynb
```

Repeat the final command for `04_anomaly_detection.ipynb`.

## Verification and limitations

The final pipeline stage reloads both persisted artefacts and checks that they
reproduce stored predictions and flags, that splits stay chronological, that lag
and rolling features are causal, that the report/CSV schemas are complete, and
that all twelve figures exist. The verified run passed 128/128 checks.

Known limitations:

- Forecast quality comes from one chronological hold-out for one household, not
  rolling-origin backtests across many homes.
- The forecast horizon is one hour ahead; recursive multi-day forecasting was
  not evaluated.
- No weather, occupancy, holiday, appliance or tariff variables are available.
- Tree models cannot extrapolate outside their training range.
- Anomaly detection is unsupervised and unlabelled; detections are candidates,
  not confirmed faults.
- The Isolation Forest contamination setting is an assumption, not an estimated
  fault prevalence.
- Saved-model verification confirms reproducibility, not correctness against
  unavailable ground truth.

Phase 5 has not started. There is no API endpoint, dashboard, database ingestion,
Airflow DAG or cloud service for these models.
