"""
WAT tool: Run inference with a trained ML model on new pipeline data.

Loads a model from the ml_models registry by model_id, extracts features for
the specified run_id using the same _ml_features.py logic as ml_train.py
(preventing training/inference skew), and writes predictions to ml_predictions.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "run_id": "uuid-of-new-run",
  "output_file": ".tmp/predictions.json"
}

Output JSON:
{
  "status": "ok",
  "model_id": "uuid",
  "model_type": "random_forest",
  "target_variable": "amr_phenotype_ciprofloxacin",
  "predictions": [
    {
      "sample_id": "S001",
      "prediction": "Resistant",
      "confidence": 0.923,
      "probabilities": {"Susceptible": 0.077, "Resistant": 0.923}
    }
  ],
  "predictions_stored": 5,
  "output_file": ".tmp/predictions.json"
}
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from _ml_features import extract_features

DEFAULT_DB = ".tmp/wat_genomics.db"


def load_model_meta(db_path: str, model_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM ml_models WHERE model_id=?", (model_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise ValueError(f"model_id '{model_id}' not found in ml_models table")
    return dict(row)


def store_predictions(db_path: str, model_meta: dict, run_id: str,
                      predictions: list) -> int:
    model_pk_row = sqlite3.connect(db_path).execute(
        "SELECT model_pk FROM ml_models WHERE model_id=?", (model_meta["model_id"],)
    ).fetchone()
    if not model_pk_row:
        return 0
    model_pk = model_pk_row[0]

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    stored = 0
    try:
        conn.execute("BEGIN")
        for pred in predictions:
            sid = pred["sample_id"]
            # Look up sample_pk (may be in either samples or phenotypic_samples)
            sample_pk_row = conn.execute(
                "SELECT sample_pk FROM samples WHERE sample_id=? AND run_id=?",
                (sid, run_id),
            ).fetchone()
            sample_pk = sample_pk_row[0] if sample_pk_row else None

            pheno_pk_row = conn.execute(
                "SELECT pheno_sample_pk FROM phenotypic_samples WHERE sample_id=? AND run_id=?",
                (sid, run_id),
            ).fetchone()
            pheno_pk = pheno_pk_row[0] if pheno_pk_row else None

            conn.execute(
                """INSERT INTO ml_predictions
                   (model_pk, sample_pk, pheno_sample_pk, run_id,
                    prediction, confidence, probabilities)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    model_pk, sample_pk, pheno_pk, run_id,
                    pred["prediction"],
                    pred["confidence"],
                    json.dumps(pred["probabilities"]),
                ),
            )
            stored += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return stored


def main():
    parser = argparse.ArgumentParser(description="Run ML inference on new pipeline data")
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
        model_id = spec.get("model_id")
        run_id = spec.get("run_id")

        if not model_id:
            raise ValueError("'model_id' is required")
        if not run_id:
            raise ValueError("'run_id' is required")

        try:
            import joblib
        except ImportError:
            raise ImportError("joblib not installed. Run: pip install joblib")

        model_meta = load_model_meta(db_path, model_id)
        model_path = model_meta.get("local_path")
        if not model_path or not Path(model_path).exists():
            # Try Google Drive download if drive_file_id is set
            drive_id = model_meta.get("drive_file_id")
            if drive_id:
                raise FileNotFoundError(
                    f"Model file not found locally at {model_path}. "
                    f"It was uploaded to Google Drive (file_id={drive_id}). "
                    "Use drive_backup.py logic to download it first."
                )
            raise FileNotFoundError(f"Model file not found: {model_path}")

        pipeline = joblib.load(model_path)

        feature_set = model_meta.get("feature_set", "genomic")
        target_variable = model_meta["target_variable"]
        filters = {"run_id": run_id}

        print(f"  Extracting features for run {run_id} ...", file=sys.stderr)
        X, _, feature_names, sample_ids = extract_features(
            db_path, feature_set, target_variable, filters
        )

        if not X:
            raise ValueError(
                f"No feature data found for run_id='{run_id}' "
                f"with feature_set='{feature_set}'. "
                "Ensure the run has been stored via db_store_run.py."
            )

        print(f"  Running inference on {len(X)} samples ...", file=sys.stderr)
        predictions_raw = pipeline.predict(X)
        probas = pipeline.predict_proba(X)
        classes = list(pipeline.classes_)

        predictions = []
        for i, sid in enumerate(sample_ids):
            prob_dict = {cls: round(float(probas[i][j]), 4)
                         for j, cls in enumerate(classes)}
            confidence = round(float(max(probas[i])), 4)
            predictions.append({
                "sample_id": sid,
                "prediction": str(predictions_raw[i]),
                "confidence": confidence,
                "probabilities": prob_dict,
            })

        stored = store_predictions(db_path, model_meta, run_id, predictions)

        result = {
            "status": "ok",
            "model_id": model_id,
            "model_type": model_meta["model_type"],
            "target_variable": target_variable,
            "predictions": predictions,
            "predictions_stored": stored,
        }

        output_file = spec.get("output_file", ".tmp/predictions.json")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        result["output_file"] = output_file

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
