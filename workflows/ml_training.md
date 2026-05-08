# ML/DL Training and Prediction Workflow

## Objective
Train machine learning models on accumulated genomic and phenotypic data stored
in the database, then use those models to predict AMR resistance phenotype,
MDR classification, or outbreak risk for newly submitted samples. Trained models
are backed up to Google Drive for portability across machines.

## Prerequisites
- Phases 1 and 2 complete: genomic runs stored + phenotypic AST data ingested
- **Minimum 20 samples** recommended; 50+ for reliable models
- Python packages: `scikit-learn`, `xgboost`, `joblib`, `numpy`

```bash
pip install scikit-learn xgboost joblib numpy
```

---

## Model Types

| Model | Use case | Speed | Interpretability |
|-------|----------|-------|-----------------|
| `random_forest` | Baseline; works well with small datasets; gives feature importances | Fast | High |
| `xgboost` | Best accuracy on tabular data; requires more tuning | Medium | Medium |
| `ann` | MLP neural network; good for combined feature sets | Slow | Low |

**Recommendation:** Train all three, compare `auc_roc_mean` from CV results,
choose the highest for production use.

---

## Feature Sets

| Feature Set | Contents | Best for |
|-------------|----------|---------|
| `genomic` | 22 AMR gene binary flags + N50, GC%, contig count, total length, SNP count | Predicting resistance from WGS |
| `phenotypic` | log2(MIC+1) + binary R flags per 23 antibiotics | Predicting related drug resistance |
| `combined` | Both sets joined on sample_id | Highest accuracy; requires both data types |

---

## Target Variables

| Target | Format | Description |
|--------|--------|-------------|
| `amr_phenotype_{antibiotic}` | Binary: Resistant / Susceptible | Predict resistance to a specific antibiotic |
| `mdr_class` | Multi-class: MDR / XDR / PDR / Susceptible | Classify MDR status |
| `outbreak_risk` | Binary: 0 / 1 | Predict outbreak potential (requires alert_records) |

Replace `{antibiotic}` with the lowercase, underscore-delimited name:
e.g., `amr_phenotype_meropenem`, `amr_phenotype_ciprofloxacin`.

---

## Step 1 — Train a Model
```bash
python tools/ml_train.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_type": "random_forest",
  "target_variable": "amr_phenotype_meropenem",
  "feature_set": "genomic",
  "filters": {
    "pathogen": "Klebsiella pneumoniae",
    "min_samples": 20
  },
  "training": {
    "k_folds": 5,
    "test_size": 0.2,
    "random_state": 42,
    "rf_n_estimators": 200
  },
  "output_dir": ".tmp/models"
}'
```

Capture `model_id` from the output — needed for prediction and backup.

**Interpreting CV results:**

| Metric | Good | Acceptable |
|--------|------|-----------|
| AUC-ROC | > 0.85 | 0.70–0.85 |
| Accuracy | > 80% | 60–80% |
| F1 (weighted) | > 0.75 | 0.55–0.75 |

If below acceptable: collect more samples or switch to `combined` feature set.

---

## Step 2 — Run Predictions on New Data
After storing a new pipeline run (via `db_store_run.py`):
```bash
python tools/ml_predict.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "run_id": "uuid-of-new-run",
  "output_file": ".tmp/predictions.json"
}'
```

Predictions are stored in `ml_predictions` table and returned in `predictions` array.
Each prediction includes `confidence` (max class probability) — low confidence
(< 0.65) indicates the sample may be an outlier or outside training distribution.

---

## Step 3 — Back Up Model to Google Drive
```bash
python tools/drive_backup.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "folder_name": "WAT_ML_Models"
}'
```
Returns `drive_url` — share with collaborating institutions so they can download
the model and run predictions without retraining.

---

## Model Comparison Workflow
Train all three model types on the same target and compare:

```bash
# Train all three
python tools/ml_train.py --input '{"model_type": "random_forest", ...}'
python tools/ml_train.py --input '{"model_type": "xgboost", ...}'
python tools/ml_train.py --input '{"model_type": "ann", ...}'

# Query model registry
python tools/db_query.py --input '{"query_type": "runs_list"}'
# Check ml_models table in DB Browser for side-by-side AUC-ROC comparison
```

---

## When to Retrain

Retrain when:
- **New data volume**: Dataset has grown by ≥ 20% since last training
- **Drift detection**: Prediction confidence drops below 0.65 for a majority of samples
- **New resistance pattern**: A novel gene or drug class appears that wasn't in training data
- **Performance degradation**: Alert-level predictions disagree with confirmed lab phenotypes

---

## GNN (Graph Neural Network) — Future Phase

GNN represents AMR data as a graph:
- **Nodes**: bacterial strains (samples), genes, facilities
- **Edges**: phylogenetic relationships, AMR gene sharing, patient transfer routes

Requires PyTorch + PyTorch Geometric:
```bash
pip install torch torch-geometric
```

This is documented for future implementation. The current pipeline's k-mer-based
phylogenetic distance matrix can serve as the adjacency matrix for a GNN.
Feature vectors from `_ml_features.py` become node features.

---

## Known Issues
- **Class imbalance**: If one class (e.g., "Resistant") has < 15% of samples,
  accuracy will be high but F1/recall for that class will be poor. Address by:
  1. Setting `class_weight="balanced"` in RandomForest (add to training spec)
  2. Using SMOTE oversampling (requires `imbalanced-learn` package)
  3. Collecting more minority class samples
- **Feature importance for ANN**: ANN does not provide intrinsic feature importances.
  The tool falls back to permutation importance, which is slower but more reliable.
- **XGBoost version**: The `use_label_encoder=False` argument is required for
  XGBoost < 2.0. If you have XGBoost 2.0+, this argument is ignored silently.
