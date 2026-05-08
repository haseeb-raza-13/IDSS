"""
WAT tool: Persist a completed pipeline run's results to the WAT Genomics database.

Reads the JSON output files produced by qc_sequences.py, snp_detection.py,
amr_detection.py, and phylogenetics.py, then writes them atomically (single
SQLite transaction) into the database. Missing files are skipped gracefully.

Call db_init.py at least once before using this tool.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",      // optional
  "run_metadata": {
    "run_id": "optional-uuid",            // auto-generated if omitted
    "researcher": "Dr. Meena Niazi",
    "study_name": "One-Health AMR Survey 2026",
    "pathogen": "Klebsiella pneumoniae",
    "source_type": "human",              // human | animal | environment | unknown
    "country": "Pakistan",
    "region": "Punjab",
    "facility": "Lahore General Hospital",
    "notes": "Outbreak investigation batch 3"
  },
  "qc_file":    ".tmp/qc_report.json",    // optional
  "snp_file":   ".tmp/snp_results.json",  // optional
  "amr_file":   ".tmp/amr_results.json",  // optional
  "phylo_file": ".tmp/phylo/results.json" // optional
}

Output JSON:
{
  "status": "ok",
  "run_id": "3f8a1c2b-...",
  "samples_stored": 5,
  "qc_records": 5,
  "snp_records": 4,
  "amr_records": 5,
  "amr_hits_total": 17,
  "snp_variants_stored": 142,
  "phylo_stored": true,
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

DEFAULT_DB = ".tmp/wat_genomics.db"
MAX_SNP_VARIANTS = 10_000  # cap per sample to avoid DB bloat


def load_json(path: str):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_sample(conn, sample_id: str, run_id: str,
                  file_path: str = None, fmt: str = None) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO samples(sample_id, run_id, file_path, format) VALUES(?,?,?,?)",
        (sample_id, run_id, file_path, fmt or "unknown"),
    )
    row = conn.execute(
        "SELECT sample_pk FROM samples WHERE sample_id=? AND run_id=?",
        (sample_id, run_id),
    ).fetchone()
    return row[0]


def store_qc(conn, run_id: str, qc_data: list) -> int:
    stored = 0
    for s in qc_data:
        sample_pk = upsert_sample(
            conn, s["sample_id"], run_id,
            s.get("file"), s.get("format", "fasta")
        )
        conn.execute(
            """INSERT INTO qc_results
               (sample_pk, run_id, format, contig_count, total_length, n50,
                gc_content, n_content, largest_contig, avg_read_length,
                avg_quality, q30_percent, pass_qc, flags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sample_pk, run_id,
                s.get("format"),
                s.get("contig_count") or s.get("read_count"),
                s.get("total_length") or s.get("total_bases"),
                s.get("n50"),
                s.get("gc_content"),
                s.get("n_content"),
                s.get("largest_contig") or s.get("max_read_length"),
                s.get("avg_read_length"),
                s.get("avg_quality"),
                s.get("q30_percent"),
                1 if s.get("pass_qc") else 0,
                json.dumps(s.get("flags", [])),
            ),
        )
        stored += 1
    return stored


def store_snp(conn, run_id: str, snp_data: list) -> tuple:
    records = 0
    variants_total = 0
    for s in snp_data:
        sample_pk = upsert_sample(conn, s["sample_id"], run_id, s.get("file"))
        conn.execute(
            """INSERT INTO snp_results(sample_pk, run_id, reference_id, total_snps, total_indels)
               VALUES(?,?,?,?,?)""",
            (sample_pk, run_id, s.get("reference_id", ""),
             s.get("total_snps", 0), s.get("total_indels", 0)),
        )
        snp_pk = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Store individual variants (capped)
        all_variants = s.get("snps", []) + s.get("indels", [])
        to_store = all_variants[:MAX_SNP_VARIANTS]
        for v in to_store:
            conn.execute(
                """INSERT INTO snp_variants(snp_pk, position, ref_allele, alt_allele, variant_type)
                   VALUES(?,?,?,?,?)""",
                (snp_pk, v.get("position"), v.get("ref_allele"),
                 v.get("alt_allele"), v.get("type", "SNP")),
            )
        variants_total += len(to_store)
        records += 1
    return records, variants_total


def store_amr(conn, run_id: str, amr_data: list) -> tuple:
    records = 0
    hits_total = 0
    for s in amr_data:
        sample_pk = upsert_sample(conn, s["sample_id"], run_id, s.get("file"))
        conn.execute(
            """INSERT INTO amr_results(sample_pk, run_id, hits_found, identity_threshold)
               VALUES(?,?,?,?)""",
            (sample_pk, run_id, s.get("hits_found", 0), None),
        )
        amr_pk = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for hit in s.get("hits", []):
            conn.execute(
                """INSERT INTO amr_hits(amr_pk, gene, drug_class, identity, gene_length)
                   VALUES(?,?,?,?,?)""",
                (amr_pk, hit.get("gene"), hit.get("drug_class"),
                 hit.get("identity"), hit.get("gene_length")),
            )
            hits_total += 1
        records += 1
    return records, hits_total


def store_phylo(conn, run_id: str, phylo_data: dict) -> bool:
    conn.execute(
        """INSERT INTO phylo_results(run_id, tree_method, kmer_size, sample_count, newick)
           VALUES(?,?,?,?,?)""",
        (run_id, phylo_data.get("tree_method"), phylo_data.get("kmer_size"),
         phylo_data.get("sample_count"), phylo_data.get("newick")),
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Store pipeline run results in the WAT DB")
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
                f"Database not found at {db_path}. Run db_init.py first."
            )

        meta = spec.get("run_metadata", {})
        run_id = meta.get("run_id") or str(uuid.uuid4())

        qc_data   = load_json(spec.get("qc_file"))
        snp_data  = load_json(spec.get("snp_file"))
        amr_data  = load_json(spec.get("amr_file"))
        phylo_data = load_json(spec.get("phylo_file"))

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            conn.execute("BEGIN")

            # Insert run header
            conn.execute(
                """INSERT OR REPLACE INTO pipeline_runs
                   (run_id, timestamp, researcher, study_name, pathogen,
                    source_type, country, region, facility, notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (run_id, utc_now(),
                 meta.get("researcher"), meta.get("study_name"),
                 meta.get("pathogen"), meta.get("source_type", "unknown"),
                 meta.get("country"), meta.get("region"),
                 meta.get("facility"), meta.get("notes")),
            )

            qc_records = store_qc(conn, run_id, qc_data or [])
            snp_records, snp_variants = store_snp(conn, run_id, snp_data or [])
            amr_records, amr_hits = store_amr(conn, run_id, amr_data or [])
            phylo_stored = store_phylo(conn, run_id, phylo_data) if phylo_data else False

            # Count distinct samples inserted
            samples_stored = conn.execute(
                "SELECT COUNT(*) FROM samples WHERE run_id=?", (run_id,)
            ).fetchone()[0]

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        result = {
            "status": "ok",
            "run_id": run_id,
            "samples_stored": samples_stored,
            "qc_records": qc_records,
            "snp_records": snp_records,
            "snp_variants_stored": snp_variants,
            "amr_records": amr_records,
            "amr_hits_total": amr_hits,
            "phylo_stored": phylo_stored,
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
