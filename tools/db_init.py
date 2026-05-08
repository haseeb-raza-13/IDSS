"""
WAT tool: Initialize (or migrate) the WAT Genomics SQLite database.

Safe to re-run at any time — all tables use CREATE TABLE IF NOT EXISTS.
Run once before the first pipeline run; subsequent calls are no-ops.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db"   // optional, default shown
}

Output JSON:
{
  "status": "ok",
  "db_path": ".tmp/wat_genomics.db",
  "tables_created": ["pipeline_runs", "samples", ...],
  "schema_version": 1
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

DEFAULT_DB = ".tmp/wat_genomics.db"
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- ============================================================
-- Core run / sample registry
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    researcher      TEXT,
    study_name      TEXT,
    pathogen        TEXT,
    source_type     TEXT CHECK(source_type IN ('human','animal','environment','unknown')),
    country         TEXT,
    region          TEXT,
    facility        TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS samples (
    sample_pk   INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   TEXT NOT NULL,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    file_path   TEXT,
    format      TEXT CHECK(format IN ('fasta','fastq','unknown')),
    UNIQUE(sample_id, run_id)
);

-- ============================================================
-- QC results
-- ============================================================

CREATE TABLE IF NOT EXISTS qc_results (
    qc_pk           INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_pk       INTEGER NOT NULL REFERENCES samples(sample_pk) ON DELETE CASCADE,
    run_id          TEXT NOT NULL,
    format          TEXT,
    contig_count    INTEGER,
    total_length    INTEGER,
    n50             INTEGER,
    gc_content      REAL,
    n_content       REAL,
    largest_contig  INTEGER,
    avg_read_length REAL,
    avg_quality     REAL,
    q30_percent     REAL,
    pass_qc         INTEGER CHECK(pass_qc IN (0,1)),
    flags           TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ============================================================
-- SNP results
-- ============================================================

CREATE TABLE IF NOT EXISTS snp_results (
    snp_pk          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_pk       INTEGER NOT NULL REFERENCES samples(sample_pk) ON DELETE CASCADE,
    run_id          TEXT NOT NULL,
    reference_id    TEXT,
    total_snps      INTEGER DEFAULT 0,
    total_indels    INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS snp_variants (
    variant_pk  INTEGER PRIMARY KEY AUTOINCREMENT,
    snp_pk      INTEGER NOT NULL REFERENCES snp_results(snp_pk) ON DELETE CASCADE,
    position    INTEGER,
    ref_allele  TEXT,
    alt_allele  TEXT,
    variant_type TEXT CHECK(variant_type IN ('SNP','INSERTION','DELETION'))
);

-- ============================================================
-- AMR results
-- ============================================================

CREATE TABLE IF NOT EXISTS amr_results (
    amr_pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_pk           INTEGER NOT NULL REFERENCES samples(sample_pk) ON DELETE CASCADE,
    run_id              TEXT NOT NULL,
    hits_found          INTEGER DEFAULT 0,
    identity_threshold  REAL,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS amr_hits (
    hit_pk      INTEGER PRIMARY KEY AUTOINCREMENT,
    amr_pk      INTEGER NOT NULL REFERENCES amr_results(amr_pk) ON DELETE CASCADE,
    gene        TEXT NOT NULL,
    drug_class  TEXT,
    identity    REAL,
    gene_length INTEGER
);

-- ============================================================
-- Phylogenetics
-- ============================================================

CREATE TABLE IF NOT EXISTS phylo_results (
    phylo_pk        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    tree_method     TEXT,
    kmer_size       INTEGER,
    sample_count    INTEGER,
    newick          TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ============================================================
-- Phenotypic / AST data
-- ============================================================

CREATE TABLE IF NOT EXISTS phenotypic_samples (
    pheno_sample_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id       TEXT NOT NULL,
    run_id          TEXT REFERENCES pipeline_runs(run_id),
    pathogen_name   TEXT,
    collection_date TEXT,
    country         TEXT,
    region          TEXT,
    facility        TEXT,
    source_type     TEXT CHECK(source_type IN ('human','animal','environment','unknown')),
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS ast_records (
    ast_pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    pheno_sample_pk     INTEGER NOT NULL REFERENCES phenotypic_samples(pheno_sample_pk) ON DELETE CASCADE,
    antibiotic          TEXT NOT NULL,
    mic_value           REAL,
    zone_diameter       REAL,
    interpretation      TEXT CHECK(interpretation IN ('S','I','R')),
    test_method         TEXT CHECK(test_method IN ('disk_diffusion','etest','broth_microdilution','other')),
    breakpoint_standard TEXT,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS mdr_classifications (
    mdr_pk              INTEGER PRIMARY KEY AUTOINCREMENT,
    pheno_sample_pk     INTEGER NOT NULL REFERENCES phenotypic_samples(pheno_sample_pk) ON DELETE CASCADE,
    run_id              TEXT,
    resistant_classes   INTEGER,
    mdr_category        TEXT CHECK(mdr_category IN ('Susceptible','MDR','XDR','PDR')),
    resistant_drug_classes TEXT
);

-- ============================================================
-- Public health alerts
-- ============================================================

CREATE TABLE IF NOT EXISTS alert_records (
    alert_pk            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    alert_level         TEXT NOT NULL CHECK(alert_level IN ('GREEN','YELLOW','ORANGE','RED')),
    alert_score         INTEGER NOT NULL,
    triggers            TEXT NOT NULL,
    high_severity_genes TEXT,
    mdr_detected        INTEGER CHECK(mdr_detected IN (0,1)),
    xdr_detected        INTEGER CHECK(xdr_detected IN (0,1)),
    outbreak_signal     INTEGER CHECK(outbreak_signal IN (0,1)),
    new_resistance      INTEGER CHECK(new_resistance IN (0,1)),
    region              TEXT,
    pathogen            TEXT,
    report_path         TEXT,
    sheets_row          INTEGER,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ============================================================
-- ML models registry
-- ============================================================

CREATE TABLE IF NOT EXISTS ml_models (
    model_pk        INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id        TEXT UNIQUE NOT NULL,
    model_type      TEXT CHECK(model_type IN ('random_forest','xgboost','ann')),
    target_variable TEXT,
    feature_set     TEXT,
    training_run_ids TEXT,
    n_samples       INTEGER,
    n_features      INTEGER,
    accuracy        REAL,
    auc_roc         REAL,
    f1_score        REAL,
    precision_score REAL,
    recall_score    REAL,
    local_path      TEXT,
    drive_file_id   TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS ml_predictions (
    pred_pk         INTEGER PRIMARY KEY AUTOINCREMENT,
    model_pk        INTEGER NOT NULL REFERENCES ml_models(model_pk),
    sample_pk       INTEGER REFERENCES samples(sample_pk),
    pheno_sample_pk INTEGER REFERENCES phenotypic_samples(pheno_sample_pk),
    run_id          TEXT,
    prediction      TEXT,
    confidence      REAL,
    probabilities   TEXT,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ============================================================
-- Performance indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_amr_hits_gene ON amr_hits(gene);
CREATE INDEX IF NOT EXISTS idx_amr_hits_drug_class ON amr_hits(drug_class);
CREATE INDEX IF NOT EXISTS idx_alert_region_date ON alert_records(region, created_at);
CREATE INDEX IF NOT EXISTS idx_ast_antibiotic ON ast_records(antibiotic, interpretation);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pathogen ON pipeline_runs(pathogen, region, timestamp);
CREATE INDEX IF NOT EXISTS idx_samples_run ON samples(run_id);
CREATE INDEX IF NOT EXISTS idx_pheno_samples_region ON phenotypic_samples(region, collection_date);
"""

CORE_TABLES = [
    "schema_version", "pipeline_runs", "samples",
    "qc_results", "snp_results", "snp_variants",
    "amr_results", "amr_hits", "phylo_results",
    "phenotypic_samples", "ast_records", "mdr_classifications",
    "alert_records", "ml_models", "ml_predictions",
]


def init_db(db_path: str) -> dict:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)

        # Record schema version (INSERT OR IGNORE so re-runs don't overwrite)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version) VALUES(?)",
            (SCHEMA_VERSION,)
        )
        conn.commit()

        # Verify tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        existing_tables = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()

    return {
        "status": "ok",
        "db_path": db_path,
        "tables_created": existing_tables,
        "schema_version": SCHEMA_VERSION,
    }


def main():
    parser = argparse.ArgumentParser(description="Initialize WAT Genomics SQLite database")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--input", help="JSON string spec")
    group.add_argument("--input-file", help="Path to JSON spec file")
    parser.add_argument("--output-file", help="Optional path to write result JSON")
    args = parser.parse_args()

    try:
        spec = {}
        if args.input_file:
            with open(args.input_file) as f:
                spec = json.load(f)
        elif args.input:
            spec = json.loads(args.input)

        db_path = spec.get("db_path", DEFAULT_DB)
        result = init_db(db_path)

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
