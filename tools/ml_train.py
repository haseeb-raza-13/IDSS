"""
WAT tool: Train an ML model on accumulated genomic and/or phenotypic data.

Supported model types: random_forest, xgboost, ann (MLP classifier).
Saves a full sklearn Pipeline (StandardScaler + classifier) via joblib.
Registers the model in the ml_models database table.

Minimum 20 samples required (configurable via filters.min_samples).

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "model_type": "random_forest",           // random_forest | xgboost | ann
  "target_variable": "amr_phenotype_ciprofloxacin",
  "feature_set": "genomic",               // genomic | phenotypic | combined
  "filters": {
    "pathogen": "Klebsiella pneumoniae",
    "run_id": "optional-specific-run",
    "min_samples": 20
  },
  "training": {
    "k_folds": 5,
    "test_size": 0.2,
    "random_state": 42,
    "rf_n_estimators": 200,
    "rf_max_depth": null,
    "xgb_n_estimators": 300,
    "xgb_learning_rate": 0.05,
    "xgb_max_depth": 6,
    "ann_hidden_layers": [64, 32],
    "ann_max_iter": 500
  },
  "output_dir": ".tmp/models"
}

Output JSON:
{
  "status": "ok",
  "model_id": "uuid",
  "model_type": "random_forest",
  "target_variable": "amr_phenotype_ciprofloxacin",
  "n_samples": 87,
  "n_features": 35,
  "cv_results": {accuracy_mean, auc_roc_mean, f1_mean, ...},
  "test_metrics": {accuracy, auc_roc, f1},
  "feature_importances": [{feature, importance}],
  "model_path": ".tmp/models/uuid.joblib",
  "model_id_registered": "uuid",
  "db_path": ".tmp/wat_genomics.db"
}
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from _ml_features import extract_features

DEFAULT_DB = ".tmp/wat_genomics.db"
DEFAULT_OUTPUT_DIR = ".tmp/models"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_model(model_type: str, training: dict, random_state: int):
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    rs = random_state

    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(
            n_estimators=training.get("rf_n_estimators", 200),
            max_depth=training.get("rf_max_depth") or None,
            random_state=rs,
            n_jobs=-1,
        )
    elif model_type == "xgboost":
        try:
            from xgboost import XGBClassifier
        except ImportError:
            raise ImportError("xgboost not installed. Run: pip install xgboost")
        clf = XGBClassifier(
            n_estimators=training.get("xgb_n_estimators", 300),
            learning_rate=training.get("xgb_learning_rate", 0.05),
            max_depth=training.get("xgb_max_depth", 6),
            random_state=rs,
            eval_metric="logloss",
            use_label_encoder=False,
        )
    elif model_type == "ann":
        from sklearn.neural_network import MLPClassifier
        hidden = training.get("ann_hidden_layers", [64, 32])
        clf = MLPClassifier(
            hidden_layer_sizes=tuple(hidden),
            max_iter=training.get("ann_max_iter", 500),
            random_state=rs,
            early_stopping=True,
            n_iter_no_change=20,
        )
    else:
        raise ValueError(
            f"Unknown model_type '{model_type}'. Use: random_forest, xgboost, ann"
        )

    return Pipeline([("scaler", StandardScaler()), ("clf", clf)])


def cross_validate_model(pipeline, X, y, k_folds: int, random_state: int) -> dict:
    import numpy as np
    from sklearn.model_selection import StratifiedKFold, cross_validate
    from sklearn.metrics import make_scorer, roc_auc_score, f1_score

    y_arr = y  # list of labels

    skf = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=random_state)

    scoring = {
        "accuracy": "accuracy",
        "f1_weighted": "f1_weighted",
        "precision_weighted": "precision_weighted",
        "recall_weighted": "recall_weighted",
    }

    # AUC-ROC only for binary classification
    unique_labels = list(set(y_arr))
    is_binary = len(unique_labels) == 2

    cv_results = cross_validate(
        pipeline, X, y_arr, cv=skf, scoring=scoring, return_train_score=False
    )

    result = {
        "accuracy_mean": round(float(np.mean(cv_results["test_accuracy"])), 4),
        "accuracy_std": round(float(np.std(cv_results["test_accuracy"])), 4),
        "f1_mean": round(float(np.mean(cv_results["test_f1_weighted"])), 4),
        "precision_mean": round(float(np.mean(cv_results["test_precision_weighted"])), 4),
        "recall_mean": round(float(np.mean(cv_results["test_recall_weighted"])), 4),
        "is_binary": is_binary,
    }

    if is_binary:
        try:
            from sklearn.model_selection import cross_val_predict
            y_pred_proba = cross_val_predict(
                pipeline, X, y_arr, cv=skf, method="predict_proba"
            )
            pos_label = unique_labels[1]
            label_map = {l: i for i, l in enumerate(unique_labels)}
            y_bin = [label_map[l] for l in y_arr]
            auc = roc_auc_score(y_bin, y_pred_proba[:, 1])
            result["auc_roc_mean"] = round(float(auc), 4)
        except Exception:
            result["auc_roc_mean"] = None

    return result


def get_feature_importances(pipeline, feature_names: list, model_type: str,
                             X_test, y_test) -> list:
    import numpy as np

    clf = pipeline.named_steps["clf"]

    if model_type == "random_forest" and hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
    elif model_type == "xgboost" and hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
    else:
        try:
            from sklearn.inspection import permutation_importance
            result = permutation_importance(pipeline, X_test, y_test, n_repeats=5,
                                            random_state=42)
            importances = result.importances_mean
        except Exception:
            return []

    pairs = sorted(
        zip(feature_names, importances), key=lambda x: x[1], reverse=True
    )
    return [
        {"feature": f, "importance": round(float(imp), 6)}
        for f, imp in pairs[:30]
    ]


def train_evaluate(pipeline, X, y, test_size: float, random_state: int,
                   feature_names: list, model_type: str) -> tuple:
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    X_arr = X
    y_arr = y

    X_train, X_test, y_train, y_test = train_test_split(
        X_arr, y_arr, test_size=test_size, random_state=random_state, stratify=y_arr
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "f1": round(f1_score(y_test, y_pred, average="weighted", zero_division=0), 4),
        "precision": round(precision_score(y_test, y_pred, average="weighted", zero_division=0), 4),
        "recall": round(recall_score(y_test, y_pred, average="weighted", zero_division=0), 4),
    }

    unique = list(set(y_arr))
    if len(unique) == 2:
        try:
            from sklearn.metrics import roc_auc_score
            y_proba = pipeline.predict_proba(X_test)
            label_map = {l: i for i, l in enumerate(pipeline.classes_)}
            y_bin = [label_map.get(l, 0) for l in y_test]
            metrics["auc_roc"] = round(roc_auc_score(y_bin, y_proba[:, 1]), 4)
        except Exception:
            metrics["auc_roc"] = None

    importances = get_feature_importances(pipeline, feature_names, model_type,
                                          X_test, y_test)
    return metrics, importances


def register_model(db_path: str, model_id: str, model_type: str,
                   target_variable: str, feature_set: str, filters: dict,
                   n_samples: int, n_features: int, cv: dict, test: dict,
                   model_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO ml_models
               (model_id, model_type, target_variable, feature_set,
                training_run_ids, n_samples, n_features,
                accuracy, auc_roc, f1_score, precision_score, recall_score,
                local_path, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                model_id, model_type, target_variable, feature_set,
                json.dumps([filters.get("run_id")] if filters.get("run_id") else []),
                n_samples, n_features,
                test.get("accuracy"), test.get("auc_roc"),
                test.get("f1"), test.get("precision"), test.get("recall"),
                model_path, utc_now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Train ML model on WAT Genomics data")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="JSON string spec")
    group.add_argument("--input-file", help="Path to JSON spec file")
    parser.add_argument("--output-file", help="Optional path to write result JSON")
    args = parser.parse_args()

    try:
        if args.input_file:
            with open(args.input_file) as f:
                spec = json.load(f)
        else:
            spec = json.loads(args.input)

        db_path = spec.get("db_path", DEFAULT_DB)
        model_type = spec.get("model_type", "random_forest")
        target_variable = spec.get("target_variable")
        feature_set = spec.get("feature_set", "genomic")
        filters = spec.get("filters", {})
        training = spec.get("training", {})
        output_dir = spec.get("output_dir", DEFAULT_OUTPUT_DIR)

        if not target_variable:
            raise ValueError("'target_variable' is required")

        min_samples = filters.get("min_samples", 20)
        random_state = training.get("random_state", 42)
        k_folds = training.get("k_folds", 5)
        test_size = training.get("test_size", 0.2)

        print(f"  Extracting features ({feature_set}) ...", file=sys.stderr)
        X, y, feature_names, sample_ids = extract_features(
            db_path, feature_set, target_variable, filters
        )

        if len(X) < min_samples:
            raise ValueError(
                f"Insufficient samples for training "
                f"(need ≥{min_samples}, found {len(X)})"
            )

        print(f"  Training {model_type} on {len(X)} samples x {len(feature_names)} features ...",
              file=sys.stderr)

        pipeline = build_model(model_type, training, random_state)

        print(f"  Cross-validating ({k_folds} folds) ...", file=sys.stderr)
        cv_results = cross_validate_model(pipeline, X, y, k_folds, random_state)

        print(f"  Final training and test evaluation ...", file=sys.stderr)
        test_metrics, importances = train_evaluate(
            pipeline, X, y, test_size, random_state, feature_names, model_type
        )

        # Save model
        try:
            import joblib
        except ImportError:
            raise ImportError("joblib not installed. Run: pip install joblib")

        model_id = str(uuid.uuid4())
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        model_path = str(Path(output_dir) / f"{model_id}.joblib")
        joblib.dump(pipeline, model_path)

        register_model(
            db_path, model_id, model_type, target_variable, feature_set, filters,
            len(X), len(feature_names), cv_results, test_metrics, model_path
        )

        result = {
            "status": "ok",
            "model_id": model_id,
            "model_type": model_type,
            "target_variable": target_variable,
            "feature_set": feature_set,
            "n_samples": len(X),
            "n_features": len(feature_names),
            "cv_results": cv_results,
            "test_metrics": test_metrics,
            "feature_importances": importances,
            "model_path": model_path,
            "model_id_registered": model_id,
            "db_path": db_path,
        }

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)

    output = json.dumps(result, indent=2)
    print(output)

    if args.output_file:
        os.makedirs(os.path.dirname(args.output_file) or ".", exist_ok=True)
        with open(args.output_file, "w") as f:
            f.write(output)


if __name__ == "__main__":
    main()
