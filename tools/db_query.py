"""
WAT tool: Query the WAT Genomics database for historical data and trend analysis.

Supports 9 query types covering AMR trends, outbreak detection, resistance rates,
sample history, and phylogenetic/model registries.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "query_type": "amr_trend",
  "filters": {
    "gene": "blaNDM-1",
    "region": "Punjab",
    "days_back": 365,
    "pathogen": "Klebsiella pneumoniae",
    "antibiotic": "Meropenem",
    "sample_id": "S001",
    "run_id": "uuid",
    "outbreak_window_days": 90,
    "outbreak_sample_threshold": 3
  },
  "output_file": ".tmp/query_result.json"   // optional
}

Supported query_type values:
  runs_list        All runs with metadata
  amr_trend        AMR gene frequency over time, per region
  mdr_trend        MDR/XDR/PDR classification counts over time
  resistance_rate  Resistance rate per antibiotic per region/period
  outbreak_check   Samples with same gene, same region, within N days
  sample_history   All results for a specific sample_id
  gene_first_seen  Earliest date a gene was detected in a region
  pheno_trend      Phenotypic resistance rate over time
  run_summary      Full result summary for one run_id

Output JSON:
{
  "status": "ok",
  "query_type": "amr_trend",
  "filters": {...},
  "results": [...],
  "count": 42
}
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = ".tmp/wat_genomics.db"


def get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}. Run db_init.py first.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query_runs_list(conn, filters: dict) -> list:
    rows = conn.execute(
        """SELECT run_id, timestamp, researcher, study_name, pathogen,
                  source_type, country, region, facility
           FROM pipeline_runs
           ORDER BY timestamp DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def query_amr_trend(conn, filters: dict) -> list:
    gene = filters.get("gene")
    region = filters.get("region")
    pathogen = filters.get("pathogen")
    days_back = filters.get("days_back", 365)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [cutoff]
    where = ["pr.timestamp >= ?"]
    if gene:
        where.append("ah.gene = ?")
        params.append(gene)
    if region:
        where.append("pr.region = ?")
        params.append(region)
    if pathogen:
        where.append("pr.pathogen = ?")
        params.append(pathogen)

    sql = f"""
        SELECT pr.timestamp, pr.region, pr.pathogen, ah.gene, ah.drug_class, ah.identity,
               s.sample_id, pr.run_id
        FROM amr_hits ah
        JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
        JOIN samples s ON ar.sample_pk = s.sample_pk
        JOIN pipeline_runs pr ON ar.run_id = pr.run_id
        WHERE {' AND '.join(where)}
        ORDER BY pr.timestamp
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_mdr_trend(conn, filters: dict) -> list:
    region = filters.get("region")
    pathogen = filters.get("pathogen")
    days_back = filters.get("days_back", 365)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [cutoff]
    where = ["ps.created_at >= ?"]
    if region:
        where.append("ps.region = ?")
        params.append(region)
    if pathogen:
        where.append("ps.pathogen_name = ?")
        params.append(pathogen)

    sql = f"""
        SELECT mc.mdr_category, COUNT(*) as count,
               strftime('%Y-%m', ps.created_at) as period
        FROM mdr_classifications mc
        JOIN phenotypic_samples ps ON mc.pheno_sample_pk = ps.pheno_sample_pk
        WHERE {' AND '.join(where)}
        GROUP BY period, mc.mdr_category
        ORDER BY period
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_resistance_rate(conn, filters: dict) -> list:
    antibiotic = filters.get("antibiotic")
    region = filters.get("region")
    pathogen = filters.get("pathogen")
    days_back = filters.get("days_back", 365)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [cutoff]
    where = ["ps.created_at >= ?"]
    if antibiotic:
        where.append("ar.antibiotic = ?")
        params.append(antibiotic)
    if region:
        where.append("ps.region = ?")
        params.append(region)
    if pathogen:
        where.append("ps.pathogen_name = ?")
        params.append(pathogen)

    sql = f"""
        SELECT ar.antibiotic, ps.region,
               strftime('%Y-%m', ps.created_at) as period,
               COUNT(*) as total,
               SUM(CASE WHEN ar.interpretation = 'R' THEN 1 ELSE 0 END) as resistant,
               ROUND(
                 100.0 * SUM(CASE WHEN ar.interpretation = 'R' THEN 1 ELSE 0 END) / COUNT(*),
                 1
               ) as resistance_rate_percent
        FROM ast_records ar
        JOIN phenotypic_samples ps ON ar.pheno_sample_pk = ps.pheno_sample_pk
        WHERE {' AND '.join(where)}
        GROUP BY ar.antibiotic, ps.region, period
        ORDER BY period, ar.antibiotic
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_outbreak_check(conn, filters: dict) -> list:
    gene = filters.get("gene")
    region = filters.get("region")
    window_days = filters.get("outbreak_window_days", 90)
    threshold = filters.get("outbreak_sample_threshold", 3)

    if not gene:
        raise ValueError("'gene' filter is required for outbreak_check query")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = [gene, cutoff]
    where = ["ah.gene = ?", "pr.timestamp >= ?"]
    if region:
        where.append("pr.region = ?")
        params.append(region)

    sql = f"""
        SELECT pr.region, pr.pathogen, COUNT(DISTINCT s.sample_id) as sample_count,
               MIN(pr.timestamp) as earliest, MAX(pr.timestamp) as latest,
               GROUP_CONCAT(DISTINCT s.sample_id) as sample_ids,
               GROUP_CONCAT(DISTINCT pr.facility) as facilities
        FROM amr_hits ah
        JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
        JOIN samples s ON ar.sample_pk = s.sample_pk
        JOIN pipeline_runs pr ON ar.run_id = pr.run_id
        WHERE {' AND '.join(where)}
        GROUP BY pr.region, pr.pathogen
        HAVING sample_count >= ?
        ORDER BY sample_count DESC
    """
    params.append(threshold)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_sample_history(conn, filters: dict) -> list:
    sample_id = filters.get("sample_id")
    if not sample_id:
        raise ValueError("'sample_id' filter is required for sample_history query")

    rows = conn.execute(
        """SELECT s.sample_id, pr.timestamp, pr.run_id, pr.pathogen, pr.region,
                  qr.total_length, qr.gc_content, qr.n50, qr.pass_qc,
                  amr.hits_found
           FROM samples s
           JOIN pipeline_runs pr ON s.run_id = pr.run_id
           LEFT JOIN qc_results qr ON qr.sample_pk = s.sample_pk
           LEFT JOIN amr_results amr ON amr.sample_pk = s.sample_pk
           WHERE s.sample_id = ?
           ORDER BY pr.timestamp""",
        (sample_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_gene_first_seen(conn, filters: dict) -> list:
    gene = filters.get("gene")
    region = filters.get("region")

    params = []
    where = []
    if gene:
        where.append("ah.gene = ?")
        params.append(gene)
    if region:
        where.append("pr.region = ?")
        params.append(region)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT ah.gene, pr.region, pr.pathogen,
               MIN(pr.timestamp) as first_seen,
               COUNT(DISTINCT s.sample_id) as total_samples
        FROM amr_hits ah
        JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
        JOIN samples s ON ar.sample_pk = s.sample_pk
        JOIN pipeline_runs pr ON ar.run_id = pr.run_id
        {where_clause}
        GROUP BY ah.gene, pr.region
        ORDER BY first_seen
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_pheno_trend(conn, filters: dict) -> list:
    return query_resistance_rate(conn, filters)


def query_run_summary(conn, filters: dict) -> dict:
    run_id = filters.get("run_id")
    if not run_id:
        raise ValueError("'run_id' filter is required for run_summary query")

    run = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if not run:
        raise ValueError(f"run_id not found: {run_id}")

    samples = conn.execute(
        "SELECT * FROM samples WHERE run_id=?", (run_id,)
    ).fetchall()

    amr_hits = conn.execute(
        """SELECT ah.gene, ah.drug_class, ah.identity, s.sample_id
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           WHERE ar.run_id=?""",
        (run_id,),
    ).fetchall()

    alert = conn.execute(
        "SELECT * FROM alert_records WHERE run_id=?", (run_id,)
    ).fetchone()

    return {
        "run": dict(run),
        "sample_count": len(samples),
        "amr_hits": [dict(h) for h in amr_hits],
        "alert": dict(alert) if alert else None,
    }


QUERY_MAP = {
    "runs_list": query_runs_list,
    "amr_trend": query_amr_trend,
    "mdr_trend": query_mdr_trend,
    "resistance_rate": query_resistance_rate,
    "outbreak_check": query_outbreak_check,
    "sample_history": query_sample_history,
    "gene_first_seen": query_gene_first_seen,
    "pheno_trend": query_pheno_trend,
    "run_summary": query_run_summary,
}


def main():
    parser = argparse.ArgumentParser(description="Query WAT Genomics database")
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
        query_type = spec.get("query_type")
        if not query_type:
            raise ValueError("'query_type' is required")
        if query_type not in QUERY_MAP:
            raise ValueError(
                f"Unknown query_type '{query_type}'. Valid: {list(QUERY_MAP.keys())}"
            )

        filters = spec.get("filters", {})
        conn = get_conn(db_path)
        try:
            raw = QUERY_MAP[query_type](conn, filters)
        finally:
            conn.close()

        count = len(raw) if isinstance(raw, list) else 1
        result = {
            "status": "ok",
            "query_type": query_type,
            "filters": filters,
            "results": raw,
            "count": count,
        }

        output_file = spec.get("output_file")
        if output_file:
            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)

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
