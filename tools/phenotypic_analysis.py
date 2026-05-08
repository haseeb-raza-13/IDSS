"""
WAT tool: Ingest and analyze phenotypic AST (Antimicrobial Susceptibility Testing) data.

Accepts CSV or Excel files. Computes resistance rates, MDR/XDR/PDR classifications,
and trend analysis. Writes results to the WAT Genomics database.

Required CSV/Excel columns:
  sample_id, pathogen_name, date (YYYY-MM-DD or YYYY-MM), location, antibiotic, interpretation (S/I/R)

Optional columns:
  mic_value, zone_diameter, test_method, source_type, facility, country, region, breakpoint_standard

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "ast_file": "/path/to/ast_data.csv",
  "run_id": "optional-existing-run-id",
  "run_metadata": {
    "researcher": "Dr. Meena Niazi",
    "study_name": "ESKAPE Surveillance 2026",
    "pathogen": "Klebsiella pneumoniae",
    "country": "Pakistan",
    "region": "Punjab",
    "source_type": "human"
  },
  "output_file": ".tmp/phenotypic_results.json"
}

Output JSON:
{
  "status": "ok",
  "run_id": "uuid",
  "samples_ingested": 120,
  "ast_records_ingested": 840,
  "mdr_summary": {"susceptible": 30, "mdr": 55, "xdr": 28, "pdr": 7},
  "resistance_rates": [...],
  "trend_analysis": [...],
  "output_file": ".tmp/phenotypic_results.json"
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

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = ".tmp/wat_genomics.db"

# Maps antibiotic name → drug class (covers ~70 common antibiotics)
DRUG_CLASS_MAP = {
    # Beta-lactams — Penicillins
    "Ampicillin": "Beta-lactam", "Amoxicillin": "Beta-lactam",
    "Amoxicillin-Clavulanate": "Beta-lactam", "Piperacillin": "Beta-lactam",
    "Piperacillin-Tazobactam": "Beta-lactam", "Oxacillin": "Beta-lactam",
    "Nafcillin": "Beta-lactam", "Cloxacillin": "Beta-lactam",
    # Beta-lactams — Cephalosporins
    "Cefazolin": "Cephalosporin", "Cephalexin": "Cephalosporin",
    "Cefuroxime": "Cephalosporin", "Cefoxitin": "Cephalosporin",
    "Ceftriaxone": "Cephalosporin", "Cefotaxime": "Cephalosporin",
    "Ceftazidime": "Cephalosporin", "Cefepime": "Cephalosporin",
    "Ceftaroline": "Cephalosporin", "Cefiderocol": "Cephalosporin",
    # Carbapenems
    "Meropenem": "Carbapenem", "Imipenem": "Carbapenem",
    "Ertapenem": "Carbapenem", "Doripenem": "Carbapenem",
    "Imipenem-Cilastatin": "Carbapenem",
    # Monobactams
    "Aztreonam": "Monobactam",
    # Quinolones / Fluoroquinolones
    "Ciprofloxacin": "Quinolone", "Levofloxacin": "Quinolone",
    "Moxifloxacin": "Quinolone", "Norfloxacin": "Quinolone",
    "Ofloxacin": "Quinolone", "Nalidixic Acid": "Quinolone",
    # Aminoglycosides
    "Gentamicin": "Aminoglycoside", "Amikacin": "Aminoglycoside",
    "Tobramycin": "Aminoglycoside", "Streptomycin": "Aminoglycoside",
    "Netilmicin": "Aminoglycoside", "Kanamycin": "Aminoglycoside",
    # Tetracyclines
    "Tetracycline": "Tetracycline", "Doxycycline": "Tetracycline",
    "Minocycline": "Tetracycline", "Tigecycline": "Tetracycline",
    # Macrolides
    "Erythromycin": "Macrolide", "Azithromycin": "Macrolide",
    "Clarithromycin": "Macrolide", "Clindamycin": "Macrolide",
    # Glycopeptides
    "Vancomycin": "Glycopeptide", "Teicoplanin": "Glycopeptide",
    # Oxazolidinones
    "Linezolid": "Oxazolidinone", "Tedizolid": "Oxazolidinone",
    # Sulfonamides
    "Trimethoprim-Sulfamethoxazole": "Sulfonamide",
    "Trimethoprim": "Sulfonamide", "Sulfamethoxazole": "Sulfonamide",
    # Polymyxins
    "Colistin": "Polymyxin", "Polymyxin B": "Polymyxin",
    # Nitrofurans
    "Nitrofurantoin": "Nitrofuran",
    # Phenicols
    "Chloramphenicol": "Phenicol",
    # Rifamycins
    "Rifampicin": "Rifamycin", "Rifampin": "Rifamycin",
    # Others
    "Fosfomycin": "Fosfomycin", "Daptomycin": "Lipopeptide",
    "Metronidazole": "Nitroimidazole",
}

# All known drug classes — used for XDR classification
ALL_DRUG_CLASSES = list(set(DRUG_CLASS_MAP.values()))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_drug_class(antibiotic: str) -> str:
    return DRUG_CLASS_MAP.get(antibiotic.strip(), "Other")


def classify_mdr(resistant_classes: list) -> str:
    n = len(resistant_classes)
    all_classes = set(ALL_DRUG_CLASSES)
    non_resistant = all_classes - set(resistant_classes)
    if n == 0:
        return "Susceptible"
    if len(non_resistant) <= 2:
        return "PDR"
    if n >= 3:
        return "MDR" if len(non_resistant) > 2 else "XDR"
    return "Susceptible"


def linear_slope(x: list, y: list) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    den = sum((xi - x_mean) ** 2 for xi in x)
    return num / den if den != 0 else 0.0


def load_ast_file(ast_file: str) -> pd.DataFrame:
    path = Path(ast_file)
    if not path.exists():
        raise FileNotFoundError(f"AST file not found: {ast_file}")
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = {"sample_id", "pathogen_name", "antibiotic", "interpretation"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"AST file missing required columns: {missing}")

    df["interpretation"] = df["interpretation"].str.upper().str.strip()
    df["antibiotic"] = df["antibiotic"].str.strip()
    df["drug_class"] = df["antibiotic"].apply(get_drug_class)
    return df


def compute_resistance_rates(df: pd.DataFrame) -> list:
    rates = []
    group_cols = ["antibiotic", "drug_class"]
    if "region" in df.columns:
        group_cols.append("region")
    if "date" in df.columns:
        df["period"] = pd.to_datetime(df["date"], errors="coerce").dt.to_period("Q").astype(str)
        group_cols.append("period")

    for keys, grp in df.groupby(group_cols, dropna=False):
        total = len(grp)
        resistant = (grp["interpretation"] == "R").sum()
        rate = round(resistant / total * 100, 1) if total > 0 else 0.0
        entry = dict(zip(group_cols, keys if isinstance(keys, tuple) else [keys]))
        entry.update({"total": int(total), "resistant": int(resistant), "rate_percent": rate})
        rates.append(entry)
    return rates


def compute_trends(df: pd.DataFrame) -> list:
    if "date" not in df.columns:
        return []

    df = df.copy()
    df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_parsed"])
    df["period"] = df["date_parsed"].dt.to_period("M")
    df["period_idx"] = df["period"].apply(lambda p: p.ordinal)

    trends = []
    group_cols = ["antibiotic"]
    if "region" in df.columns:
        group_cols.append("region")

    for keys, grp in df.groupby(group_cols, dropna=False):
        period_data = (
            grp.groupby("period_idx")
            .apply(lambda g: round((g["interpretation"] == "R").mean() * 100, 1))
            .reset_index()
        )
        period_data.columns = ["period_idx", "rate"]
        if len(period_data) < 2:
            continue

        xs = period_data["period_idx"].tolist()
        ys = period_data["rate"].tolist()
        slope = linear_slope(xs, ys)

        entry = {"antibiotic": keys[0] if isinstance(keys, tuple) else keys}
        if "region" in group_cols and isinstance(keys, tuple) and len(keys) > 1:
            entry["region"] = keys[1]
        entry.update({
            "trend": "rising" if slope > 0.5 else "falling" if slope < -0.5 else "stable",
            "slope_percent_per_month": round(slope, 3),
            "data_points": period_data["rate"].tolist(),
        })
        trends.append(entry)
    return trends


def store_phenotypic(conn, df: pd.DataFrame, run_id: str, meta: dict) -> tuple:
    samples_stored = 0
    ast_stored = 0

    for sample_id, grp in df.groupby("sample_id"):
        first = grp.iloc[0]
        conn.execute(
            """INSERT INTO phenotypic_samples
               (sample_id, run_id, pathogen_name, collection_date, country, region,
                facility, source_type)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                str(sample_id),
                run_id,
                str(first.get("pathogen_name", meta.get("pathogen", ""))),
                str(first.get("date", "")),
                str(first.get("country", meta.get("country", ""))),
                str(first.get("region", meta.get("region", ""))),
                str(first.get("facility", meta.get("facility", ""))),
                str(first.get("source_type", meta.get("source_type", "unknown"))),
            ),
        )
        pheno_pk = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        samples_stored += 1

        # AST records
        for _, row in grp.iterrows():
            interp = str(row.get("interpretation", "")).upper()
            if interp not in ("S", "I", "R"):
                continue
            conn.execute(
                """INSERT INTO ast_records
                   (pheno_sample_pk, antibiotic, mic_value, zone_diameter,
                    interpretation, test_method, breakpoint_standard)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    pheno_pk,
                    str(row.get("antibiotic", "")),
                    row.get("mic_value") if pd.notna(row.get("mic_value")) else None,
                    row.get("zone_diameter") if pd.notna(row.get("zone_diameter")) else None,
                    interp,
                    str(row.get("test_method", "other")),
                    str(row.get("breakpoint_standard", "")),
                ),
            )
            ast_stored += 1

        # MDR classification
        resistant_classes = (
            grp[grp["interpretation"] == "R"]["drug_class"].unique().tolist()
        )
        category = classify_mdr(resistant_classes)
        conn.execute(
            """INSERT INTO mdr_classifications
               (pheno_sample_pk, run_id, resistant_classes, mdr_category, resistant_drug_classes)
               VALUES(?,?,?,?,?)""",
            (pheno_pk, run_id, len(resistant_classes), category,
             json.dumps(resistant_classes)),
        )

    return samples_stored, ast_stored


def main():
    parser = argparse.ArgumentParser(description="Ingest and analyze AST phenotypic data")
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
        if not Path(db_path).exists():
            raise FileNotFoundError(
                f"Database not found: {db_path}. Run db_init.py first."
            )

        meta = spec.get("run_metadata", {})
        run_id = spec.get("run_id") or str(uuid.uuid4())

        df = load_ast_file(spec["ast_file"])

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN")

            # Ensure run exists
            existing = conn.execute(
                "SELECT run_id FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO pipeline_runs
                       (run_id, timestamp, researcher, study_name, pathogen,
                        source_type, country, region, facility)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (run_id, utc_now(),
                     meta.get("researcher"), meta.get("study_name"),
                     meta.get("pathogen"), meta.get("source_type", "unknown"),
                     meta.get("country"), meta.get("region"), meta.get("facility")),
                )

            samples_stored, ast_stored = store_phenotypic(conn, df, run_id, meta)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        resistance_rates = compute_resistance_rates(df)
        trend_analysis = compute_trends(df)

        # MDR summary
        mdr_counts = {"susceptible": 0, "mdr": 0, "xdr": 0, "pdr": 0}
        for _, grp in df.groupby("sample_id"):
            resistant_classes = (
                grp[grp["interpretation"] == "R"]["drug_class"].unique().tolist()
            )
            cat = classify_mdr(resistant_classes).lower()
            if cat in mdr_counts:
                mdr_counts[cat] += 1

        result = {
            "status": "ok",
            "run_id": run_id,
            "samples_ingested": samples_stored,
            "ast_records_ingested": ast_stored,
            "mdr_summary": mdr_counts,
            "resistance_rates": resistance_rates,
            "trend_analysis": trend_analysis,
            "db_path": db_path,
        }

        output_file = spec.get("output_file", ".tmp/phenotypic_results.json")
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
