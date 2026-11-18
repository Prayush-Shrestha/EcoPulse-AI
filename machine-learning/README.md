# Machine Learning

Forecasting and anomaly-detection experiments live here. **Phase 1 contains no
models and no predictions**; this directory is a prepared workspace for later
phases.

## Boundaries

- `src/` - feature engineering, training, evaluation, and inference modules.
- `notebooks/` - experiments and analysis, not production code.
- `models/` - local serialised artefacts (`.joblib`), ignored by Git.

## Environment

Keep this environment separate from the API runtime and from data engineering:

```powershell
cd D:\ai\EcoPulse-AI\machine-learning
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Evaluation rules

1. Use chronological train/validation/test splits for time-series data.
2. Prevent leakage from future readings into feature windows.
3. Record metrics, random seeds, feature definitions, and data cut-off dates.
4. Compare against a simple seasonal baseline before claiming model quality.
5. Persist model artefacts locally only; no cloud model registry in this project.

## Phase 1 status

- No training data, models, or metrics exist.
- No API endpoint serves predictions.
- No dependency has been installed in the backend environment.
