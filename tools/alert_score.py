"""
WAT tool: Score a pipeline run for public health threat level.

Reads AMR hits, MDR classifications, and historical outbreak patterns from the
database. Produces an alert level (GREEN / YELLOW / ORANGE / RED) and writes the
alert record to the database for longitudinal tracking.

Scoring (0–100, capped at 100):
  MDR pattern (≥3 drug classes resistant)   +20
  XDR pattern                                +40
  High-severity gene detected                +25 each, capped at +50
    (blaNDM-1, blaKPC-2, blaOXA-48, mcr-1, vanA, blaVIM, blaIMP)
  Outbreak signal (≥threshold samples,       +30
    same gene, same region, within window)
  New resistance (first detection in region) +15

Alert levels:
  GREEN   0–19
  YELLOW  20–44
  ORANGE  45–69
  RED     70–100

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "uuid",
  "outbreak_window_days": 90,
  "outbreak_sample_threshold": 3,
  "output_file": ".tmp/alert_result.json"
}

Output JSON:
{
  "status": "ok",
  "run_id": "uuid",
  "alert_level": "RED",
  "alert_score": 87,
  "triggers": ["NDM-1 detected in 2 samples", "OUTBREAK SIGNAL: ..."],
  "high_severity_genes": ["blaNDM-1"],
  "mdr_detected": true,
  "xdr_detected": false,
  "outbreak_signal": true,
  "new_resistance": true,
  "region": "Punjab",
  "pathogen": "Klebsiella pneumoniae"
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

HIGH_SEVERITY_GENES = {
    "blaNDM-1", "blaNDM-5", "blaKPC-2", "blaKPC-3",
    "blaOXA-48", "blaOXA-232", "mcr-1", "mcr-2",
    "vanA", "blaVIM-1", "blaVIM-2", "blaIMP-1",
}

ALERT_LEVELS = [
    (70, "RED"),
    (45, "ORANGE"),
    (20, "YELLOW"),
    (0,  "GREEN"),
]


def level_from_score(score: int) -> str:
    for threshold, level in ALERT_LEVELS:
        if score >= threshold:
            return level
    return "GREEN"


def get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_run_info(conn, run_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"run_id not found in database: {run_id}")
    return dict(row)


def get_amr_hits_for_run(conn, run_id: str) -> list:
    rows = conn.execute(
        """SELECT ah.gene, ah.drug_class, ah.identity, s.sample_id
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           WHERE ar.run_id = ?""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_mdr_for_run(conn, run_id: str) -> list:
    rows = conn.execute(
        """SELECT mc.mdr_category, mc.resistant_classes, mc.resistant_drug_classes
           FROM mdr_classifications mc
           WHERE mc.run_id = ?""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def check_outbreak(conn, gene: str, region: str,
                   window_days: int, threshold: int) -> dict:
    if not region:
        return {"detected": False}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    row = conn.execute(
        """SELECT COUNT(DISTINCT s.sample_id) as cnt,
                  MIN(pr.timestamp) as earliest,
                  MAX(pr.timestamp) as latest
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           JOIN pipeline_runs pr ON ar.run_id = pr.run_id
           WHERE ah.gene = ? AND pr.region = ? AND pr.timestamp >= ?""",
        (gene, region, cutoff),
    ).fetchone()
    cnt = row["cnt"] if row else 0
    return {
        "detected": cnt >= threshold,
        "sample_count": cnt,
        "window_days": window_days,
        "earliest": row["earliest"] if row else None,
        "latest": row["latest"] if row else None,
    }


def check_new_resistance(conn, gene: str, region: str, run_timestamp: str) -> bool:
    if not region:
        return False
    row = conn.execute(
        """SELECT MIN(pr.timestamp) as first_seen
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           JOIN pipeline_runs pr ON ar.run_id = pr.run_id
           WHERE ah.gene = ? AND pr.region = ?""",
        (gene, region),
    ).fetchone()
    if not row or not row["first_seen"]:
        return True  # no prior record
    # True if the earliest sighting is within this run's timestamp minute
    return row["first_seen"][:16] >= run_timestamp[:16]


def compute_alert(conn, run_id: str, outbreak_window: int,
                  outbreak_threshold: int) -> dict:
    run_info = get_run_info(conn, run_id)
    region = run_info.get("region", "")
    pathogen = run_info.get("pathogen", "")

    hits = get_amr_hits_for_run(conn, run_id)
    mdr_records = get_mdr_for_run(conn, run_id)

    score = 0
    triggers = []
    high_sev_found = []

    # --- MDR / XDR scoring ---
    mdr_detected = any(r["mdr_category"] == "MDR" for r in mdr_records)
    xdr_detected = any(r["mdr_category"] == "XDR" for r in mdr_records)
    pdr_detected = any(r["mdr_category"] == "PDR" for r in mdr_records)

    if pdr_detected:
        score += 40
        triggers.append("PDR (Pan-Drug Resistance) detected")
    elif xdr_detected:
        score += 40
        triggers.append("XDR (Extensively Drug-Resistant) pattern detected")
    elif mdr_detected:
        score += 20
        mdr_count = sum(1 for r in mdr_records if r["mdr_category"] == "MDR")
        triggers.append(f"MDR pattern detected in {mdr_count} sample(s)")

    # --- High-severity gene scoring ---
    all_genes = {h["gene"] for h in hits}
    sev_genes_found = all_genes & HIGH_SEVERITY_GENES
    sev_score = min(len(sev_genes_found) * 25, 50)
    if sev_genes_found:
        score += sev_score
        high_sev_found = sorted(sev_genes_found)
        gene_counts = {}
        for h in hits:
            if h["gene"] in sev_genes_found:
                gene_counts[h["gene"]] = gene_counts.get(h["gene"], 0) + 1
        for g, cnt in gene_counts.items():
            triggers.append(f"HIGH-SEVERITY: {g} detected in {cnt} sample(s)")

    # --- Outbreak signal ---
    outbreak_signal = False
    for gene in sev_genes_found:
        ob = check_outbreak(conn, gene, region, outbreak_window, outbreak_threshold)
        if ob["detected"]:
            outbreak_signal = True
            score += 30
            triggers.append(
                f"OUTBREAK SIGNAL: {gene} found in {ob['sample_count']} samples "
                f"from {region} within {outbreak_window} days "
                f"({ob['earliest']} — {ob['latest']})"
            )
            break  # count outbreak bonus once

    # --- New resistance ---
    new_resistance = False
    for gene in sev_genes_found | all_genes:
        if check_new_resistance(conn, gene, region, run_info["timestamp"]):
            new_resistance = True
            score += 15
            triggers.append(
                f"NEW RESISTANCE: {gene} first detected in {region or 'this region'}"
            )
            break  # count novelty bonus once

    score = min(score, 100)
    alert_level = level_from_score(score)

    if not triggers:
        triggers.append("No high-risk resistance patterns detected in this run")

    return {
        "run_id": run_id,
        "alert_level": alert_level,
        "alert_score": score,
        "triggers": triggers,
        "high_severity_genes": high_sev_found,
        "mdr_detected": mdr_detected,
        "xdr_detected": xdr_detected,
        "outbreak_signal": outbreak_signal,
        "new_resistance": new_resistance,
        "region": region,
        "pathogen": pathogen,
        "samples_in_run": len({h["sample_id"] for h in hits}),
    }


def write_alert_to_db(conn, alert: dict, report_path: str = None) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO alert_records
           (run_id, alert_level, alert_score, triggers, high_severity_genes,
            mdr_detected, xdr_detected, outbreak_signal, new_resistance,
            region, pathogen, report_path)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            alert["run_id"],
            alert["alert_level"],
            alert["alert_score"],
            json.dumps(alert["triggers"]),
            json.dumps(alert["high_severity_genes"]),
            1 if alert["mdr_detected"] else 0,
            1 if alert["xdr_detected"] else 0,
            1 if alert["outbreak_signal"] else 0,
            1 if alert["new_resistance"] else 0,
            alert["region"],
            alert["pathogen"],
            report_path,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description="Score a run for public health threat level")
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
        run_id = spec.get("run_id")
        if not run_id:
            raise ValueError("'run_id' is required")

        outbreak_window = spec.get("outbreak_window_days", 90)
        outbreak_threshold = spec.get("outbreak_sample_threshold", 3)

        conn = get_conn(db_path)
        try:
            alert = compute_alert(conn, run_id, outbreak_window, outbreak_threshold)
            conn.execute("BEGIN")
            write_alert_to_db(conn, alert)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        result = {"status": "ok", **alert}

        output_file = spec.get("output_file", ".tmp/alert_result.json")
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
