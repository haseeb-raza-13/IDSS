"""
Shared feature engineering module for ML tools.

This is NOT a standalone WAT tool — it is a private helper imported by
ml_train.py and ml_predict.py to ensure that training and inference use
identical feature extraction logic (preventing training/inference skew).

Exported function:
  extract_features(db_path, feature_set, target_variable, filters)
    -> (X: list[list], y: list, feature_names: list[str], sample_ids: list[str])

Supported feature_set values:
  "genomic"    - AMR gene presence/absence + genome QC metrics + SNP counts
  "phenotypic" - MIC values (log2-transformed) + binary R flags per antibiotic
  "combined"   - Both sets joined on sample_id

Supported target_variable formats:
  "amr_phenotype_{antibiotic}"  - binary resistant/susceptible (e.g. "amr_phenotype_ciprofloxacin")
  "mdr_class"                   - MDR / XDR / PDR / Susceptible (multi-class)
  "outbreak_risk"               - binary 0/1 from alert_records
"""

import json
import math
import sqlite3
from pathlib import Path

# The 22 AMR genes tracked in amr_hits — one binary feature per gene
AMR_GENE_FEATURES = [
    "blaTEM-1", "blaSHV-1", "blaCTX-M-15", "blaKPC-2", "blaNDM-1",
    "blaOXA-48", "mecA", "vanA", "vanB", "tetA", "tetB", "tetM",
    "sul1", "sul2", "aac(6')-Ib", "aph(3')-Ia", "qnrS1", "qnrB1",
    "ermB", "ermA", "mcr-1", "cfr",
]

# Antibiotics used as phenotypic features (those with enough data typically)
PHENO_ANTIBIOTICS = [
    "Ampicillin", "Amoxicillin-Clavulanate", "Piperacillin-Tazobactam",
    "Ceftriaxone", "Ceftazidime", "Cefepime", "Meropenem", "Imipenem",
    "Ertapenem", "Ciprofloxacin", "Levofloxacin", "Gentamicin", "Amikacin",
    "Tobramycin", "Tetracycline", "Tigecycline", "Vancomycin", "Linezolid",
    "Trimethoprim-Sulfamethoxazole", "Colistin", "Chloramphenicol",
    "Erythromycin", "Azithromycin",
]


def _get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_genomic_features(conn, filters: dict) -> dict:
    """
    Return {sample_id: feature_dict} for all samples matching filters.
    Features: one binary per AMR gene + numeric QC metrics + SNP count.
    """
    run_id = filters.get("run_id")
    pathogen = filters.get("pathogen")

    params = []
    where_parts = []
    if run_id:
        where_parts.append("ar.run_id = ?")
        params.append(run_id)
    if pathogen:
        where_parts.append("pr.pathogen = ?")
        params.append(pathogen)
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    # AMR gene hits
    amr_rows = conn.execute(
        f"""SELECT s.sample_id, ah.gene
            FROM amr_hits ah
            JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
            JOIN samples s ON ar.sample_pk = s.sample_pk
            JOIN pipeline_runs pr ON ar.run_id = pr.run_id
            {where}""",
        params,
    ).fetchall()

    # QC metrics
    qc_rows = conn.execute(
        f"""SELECT s.sample_id, qr.n50, qr.gc_content, qr.contig_count,
                   qr.total_length, qr.n_content
            FROM qc_results qr
            JOIN samples s ON qr.sample_pk = s.sample_pk
            JOIN pipeline_runs pr ON qr.run_id = pr.run_id
            {where}""",
        params,
    ).fetchall()

    # SNP counts
    snp_rows = conn.execute(
        f"""SELECT s.sample_id, sr.total_snps, sr.total_indels
            FROM snp_results sr
            JOIN samples s ON sr.sample_pk = s.sample_pk
            JOIN pipeline_runs pr ON sr.run_id = pr.run_id
            {where}""",
        params,
    ).fetchall()

    # Build feature dicts per sample
    features = {}

    for row in qc_rows:
        sid = row["sample_id"]
        features[sid] = {
            f"gene_{g.replace('-','_').replace('(','').replace(')','').replace(\"'\",'')}": 0
            for g in AMR_GENE_FEATURES
        }
        features[sid].update({
            "qc_n50": row["n50"] or 0,
            "qc_gc_content": row["gc_content"] or 0.0,
            "qc_contig_count": row["contig_count"] or 0,
            "qc_total_length": row["total_length"] or 0,
            "qc_n_content": row["n_content"] or 0.0,
            "snp_total_snps": 0,
            "snp_total_indels": 0,
        })

    for row in amr_rows:
        sid = row["sample_id"]
        if sid not in features:
            features[sid] = {
                f"gene_{g.replace('-','_').replace('(','').replace(')','').replace(\"'\",'')}": 0
                for g in AMR_GENE_FEATURES
            }
        gene_key = (
            "gene_"
            + row["gene"]
            .replace("-", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("'", "")
        )
        if gene_key in features[sid]:
            features[sid][gene_key] = 1

    for row in snp_rows:
        sid = row["sample_id"]
        if sid in features:
            features[sid]["snp_total_snps"] = row["total_snps"] or 0
            features[sid]["snp_total_indels"] = row["total_indels"] or 0

    return features


def _fetch_phenotypic_features(conn, filters: dict) -> dict:
    """
    Return {sample_id: feature_dict} from ast_records.
    Features: log2(MIC+1) per antibiotic + binary R flag per antibiotic.
    Missing values are imputed with median (computed across all samples).
    """
    run_id = filters.get("run_id")
    pathogen = filters.get("pathogen")

    params = []
    where_parts = []
    if run_id:
        where_parts.append("ps.run_id = ?")
        params.append(run_id)
    if pathogen:
        where_parts.append("ps.pathogen_name = ?")
        params.append(pathogen)
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    rows = conn.execute(
        f"""SELECT ps.sample_id, ar.antibiotic, ar.mic_value, ar.interpretation
            FROM ast_records ar
            JOIN phenotypic_samples ps ON ar.pheno_sample_pk = ps.pheno_sample_pk
            {where}""",
        params,
    ).fetchall()

    # Collect per sample
    raw = {}
    for row in rows:
        sid = row["sample_id"]
        abx = row["antibiotic"]
        raw.setdefault(sid, {})[abx] = {
            "mic": row["mic_value"],
            "interp": (row["interpretation"] or "").upper(),
        }

    # Compute medians for imputation
    mic_values_by_abx = {}
    for sid_data in raw.values():
        for abx, vals in sid_data.items():
            if vals["mic"] is not None:
                mic_values_by_abx.setdefault(abx, []).append(vals["mic"])

    mic_medians = {}
    for abx, vals in mic_values_by_abx.items():
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        mic_medians[abx] = sorted_vals[n // 2]

    # Build feature matrix
    features = {}
    for sid, abx_data in raw.items():
        feat = {}
        for abx in PHENO_ANTIBIOTICS:
            safe_name = abx.replace("-", "_").replace(" ", "_")
            data = abx_data.get(abx, {})
            mic = data.get("mic")
            if mic is None:
                mic = mic_medians.get(abx, 0.0)
            feat[f"pheno_mic_log2_{safe_name}"] = math.log2(mic + 1) if mic else 0.0
            feat[f"pheno_R_{safe_name}"] = 1 if data.get("interp") == "R" else 0
        features[sid] = feat

    return features


def _fetch_labels(conn, target_variable: str, sample_ids: list,
                  filters: dict) -> dict:
    """Return {sample_id: label} for the given target variable."""
    run_id = filters.get("run_id")

    if target_variable.startswith("amr_phenotype_"):
        # "amr_phenotype_ciprofloxacin" → antibiotic = "Ciprofloxacin"
        antibiotic_raw = target_variable[len("amr_phenotype_"):]
        antibiotic = antibiotic_raw.replace("_", " ").title()

        params = [antibiotic] + list(sample_ids)
        placeholders = ",".join("?" * len(sample_ids))
        rows = conn.execute(
            f"""SELECT ps.sample_id, ar.interpretation
                FROM ast_records ar
                JOIN phenotypic_samples ps ON ar.pheno_sample_pk = ps.pheno_sample_pk
                WHERE ar.antibiotic = ? AND ps.sample_id IN ({placeholders})""",
            params,
        ).fetchall()
        return {
            r["sample_id"]: ("Resistant" if r["interpretation"] == "R" else "Susceptible")
            for r in rows
        }

    elif target_variable == "mdr_class":
        params = list(sample_ids)
        placeholders = ",".join("?" * len(sample_ids))
        rows = conn.execute(
            f"""SELECT ps.sample_id, mc.mdr_category
                FROM mdr_classifications mc
                JOIN phenotypic_samples ps ON mc.pheno_sample_pk = ps.pheno_sample_pk
                WHERE ps.sample_id IN ({placeholders})""",
            params,
        ).fetchall()
        return {r["sample_id"]: r["mdr_category"] for r in rows}

    elif target_variable == "outbreak_risk":
        if not run_id:
            raise ValueError("'run_id' filter required for outbreak_risk target")
        row = conn.execute(
            "SELECT outbreak_signal FROM alert_records WHERE run_id=?", (run_id,)
        ).fetchone()
        outbreak = 1 if (row and row["outbreak_signal"]) else 0
        return {sid: outbreak for sid in sample_ids}

    else:
        raise ValueError(
            f"Unknown target_variable '{target_variable}'. "
            "Use 'amr_phenotype_{{antibiotic}}', 'mdr_class', or 'outbreak_risk'."
        )


def extract_features(
    db_path: str,
    feature_set: str,
    target_variable: str,
    filters: dict,
):
    """
    Extract feature matrix and labels from the database.

    Returns:
        X             - list[list[float]], one row per sample
        y             - list of labels (str or int)
        feature_names - list[str] of column names in X
        sample_ids    - list[str] aligned with X and y
    """
    if feature_set not in ("genomic", "phenotypic", "combined"):
        raise ValueError(f"Invalid feature_set '{feature_set}'")

    conn = _get_conn(db_path)
    try:
        genomic_feats = {}
        pheno_feats = {}

        if feature_set in ("genomic", "combined"):
            genomic_feats = _fetch_genomic_features(conn, filters)
        if feature_set in ("phenotypic", "combined"):
            pheno_feats = _fetch_phenotypic_features(conn, filters)

        if feature_set == "genomic":
            all_sample_ids = list(genomic_feats.keys())
        elif feature_set == "phenotypic":
            all_sample_ids = list(pheno_feats.keys())
        else:  # combined
            all_sample_ids = list(
                set(genomic_feats.keys()) & set(pheno_feats.keys())
            )

        if not all_sample_ids:
            return [], [], [], []

        labels = _fetch_labels(conn, target_variable, all_sample_ids, filters)
    finally:
        conn.close()

    # Keep only samples that have labels
    sample_ids = [s for s in all_sample_ids if s in labels]
    if not sample_ids:
        return [], [], [], []

    # Build feature names from first sample
    first_id = sample_ids[0]
    feature_names = []
    if feature_set in ("genomic", "combined") and first_id in genomic_feats:
        feature_names += sorted(genomic_feats[first_id].keys())
    if feature_set in ("phenotypic", "combined") and first_id in pheno_feats:
        feature_names += sorted(pheno_feats[first_id].keys())

    X = []
    y = []
    for sid in sample_ids:
        row = []
        if feature_set in ("genomic", "combined"):
            gf = genomic_feats.get(sid, {})
            row += [float(gf.get(f, 0)) for f in sorted(
                genomic_feats.get(first_id, {}).keys()
            )]
        if feature_set in ("phenotypic", "combined"):
            pf = pheno_feats.get(sid, {})
            row += [float(pf.get(f, 0)) for f in sorted(
                pheno_feats.get(first_id, {}).keys()
            )]
        X.append(row)
        y.append(labels[sid])

    return X, y, feature_names, sample_ids
