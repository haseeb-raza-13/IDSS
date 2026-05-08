"""
WAT tool: Generate a Word document public health alert brief.

Reads the alert JSON produced by alert_score.py and the AMR data from the
database, then produces a structured Word document targeted at public health
officials and epidemiologists (non-technical language for the summary;
technical tables for the annexure).

Imports build_document() from write_word_doc.py — same pattern as
generate_genomics_report.py.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "run_id": "uuid",                        // optional if alert_file supplied
  "output_path": ".tmp/alert_report.docx"
}

Output JSON:
{
  "status": "ok",
  "output_path": ".tmp/alert_report.docx",
  "alert_level": "RED"
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
from write_word_doc import build_document

DEFAULT_DB = ".tmp/wat_genomics.db"

RECOMMENDATIONS = {
    "RED": [
        "Immediately notify the National Institute of Health (NIH) / national public health authority.",
        "Activate enhanced infection prevention and control (IPC) protocols in all affected facilities.",
        "Initiate contact tracing and screening of exposed patients and healthcare workers.",
        "Restrict movement of affected patients between wards; implement cohort isolation.",
        "Convene an emergency multi-disciplinary team (ID specialist, IPC, microbiology, administration).",
        "Report to WHO IHR focal point if the pathogen meets international concern criteria.",
        "Increase sampling frequency; send isolates to reference laboratory for whole-genome sequencing.",
        "Review and restrict empirical antibiotic prescribing for the affected pathogen.",
    ],
    "ORANGE": [
        "Notify the regional / provincial public health unit within 24 hours.",
        "Increase surveillance sampling frequency (double current rate).",
        "Implement enhanced hand hygiene and contact precautions in affected wards.",
        "Review antibiotic stewardship guidelines for the detected resistance class.",
        "Convene an IPC team review within 72 hours.",
        "Submit a situation report to the national AMR surveillance programme.",
    ],
    "YELLOW": [
        "Flag isolates for secondary confirmation by reference laboratory.",
        "Increase monitoring of patients harboring the organism.",
        "Notify ward infection control nurse; assess environmental contamination risk.",
        "Review prescribing patterns for affected antibiotic classes.",
        "Document findings in the institutional AMR surveillance log.",
    ],
    "GREEN": [
        "No immediate intervention required.",
        "Continue routine AMR surveillance at the standard sampling frequency.",
        "Maintain baseline infection prevention and control measures.",
        "Review at the next scheduled AMR committee meeting.",
    ],
}

LEVEL_DESCRIPTIONS = {
    "RED": (
        "CRITICAL — Immediate action required. A serious AMR threat has been identified "
        "that poses an imminent risk to patients and the broader community. This alert "
        "requires escalation to national public health authorities."
    ),
    "ORANGE": (
        "HIGH — Urgent attention required. Significant antimicrobial resistance has been "
        "detected. Regional public health authorities should be notified and enhanced "
        "surveillance initiated within 24–48 hours."
    ),
    "YELLOW": (
        "MODERATE — Elevated risk detected. Resistance patterns warrant closer monitoring "
        "and laboratory confirmation. Routine infection control measures should be reviewed."
    ),
    "GREEN": (
        "LOW — No significant resistance threat detected. Results are within expected "
        "baseline parameters. Continue routine surveillance."
    ),
}


def get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_run_amr_detail(conn, run_id: str) -> list:
    rows = conn.execute(
        """SELECT ah.gene, ah.drug_class, ah.identity, s.sample_id
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           WHERE ar.run_id = ?
           ORDER BY ah.drug_class, ah.gene""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_outbreak_context(conn, alert: dict) -> list:
    if not alert.get("outbreak_signal") or not alert.get("region"):
        return []
    rows = conn.execute(
        """SELECT DISTINCT s.sample_id, pr.timestamp, pr.facility, pr.researcher
           FROM amr_hits ah
           JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
           JOIN samples s ON ar.sample_pk = s.sample_pk
           JOIN pipeline_runs pr ON ar.run_id = pr.run_id
           WHERE pr.region = ? AND ah.gene IN ({})
           ORDER BY pr.timestamp""".format(
            ",".join("?" for _ in alert.get("high_severity_genes", []))
        ),
        [alert["region"]] + alert.get("high_severity_genes", []),
    ).fetchall()
    return [dict(r) for r in rows]


def build_alert_report(alert: dict, amr_detail: list, outbreak_ctx: list,
                       run_info: dict, output_path: str) -> str:
    level = alert.get("alert_level", "GREEN")
    score = alert.get("alert_score", 0)
    pathogen = alert.get("pathogen", "Unknown pathogen")
    region = alert.get("region", "Unknown region")
    triggers = alert.get("triggers", [])

    # Aggregate gene summary
    gene_summary = {}
    for h in amr_detail:
        g = h["gene"]
        if g not in gene_summary:
            gene_summary[g] = {"drug_class": h["drug_class"], "count": 0,
                                "max_identity": 0.0}
        gene_summary[g]["count"] += 1
        gene_summary[g]["max_identity"] = max(
            gene_summary[g]["max_identity"], h.get("identity") or 0.0
        )

    amr_table_rows = [
        [gene, info["drug_class"], str(info["count"]),
         f"{info['max_identity']*100:.1f}%"]
        for gene, info in sorted(gene_summary.items())
    ] or [["None detected", "—", "—", "—"]]

    outbreak_table_rows = [
        [r["sample_id"], r["timestamp"][:10], r["facility"] or "—",
         r["researcher"] or "—"]
        for r in outbreak_ctx
    ] or []

    sections = [
        {
            "heading": f"ALERT LEVEL: {level}  |  Score: {score}/100",
            "heading_level": 1,
            "paragraphs": [
                LEVEL_DESCRIPTIONS[level],
                f"Pathogen: {pathogen}",
                f"Region / Facility: {region}",
                f"Report Date: {run_info.get('timestamp', '')[:10]}",
                f"Researcher: {run_info.get('researcher', 'N/A')}",
                f"Study: {run_info.get('study_name', 'N/A')}",
            ],
        },
        {
            "heading": "Executive Summary",
            "heading_level": 2,
            "paragraphs": [
                f"This report summarises the antimicrobial resistance (AMR) findings "
                f"from {alert.get('samples_in_run', 'N/A')} bacterial isolate(s) submitted "
                f"for genomic analysis from {region}. "
                f"{'A high-severity resistance pattern has been identified requiring immediate action.' if level in ('RED','ORANGE') else 'Findings are within the expected range for the surveillance period.'} "
                f"{'An outbreak signal has been triggered based on historical database comparison.' if alert.get('outbreak_signal') else ''}",
            ],
        },
        {
            "heading": "Alert Triggers",
            "heading_level": 2,
            "bullet_list": triggers,
        },
        {
            "heading": "AMR Findings",
            "heading_level": 2,
            "paragraphs": [
                f"Total AMR genes detected: {len(gene_summary)}. "
                f"High-severity genes: {', '.join(alert.get('high_severity_genes', [])) or 'None'}."
            ],
            "table": {
                "headers": ["Resistance Gene", "Drug Class", "Samples Affected", "Max k-mer Identity"],
                "rows": amr_table_rows,
            },
        },
    ]

    if outbreak_ctx:
        sections.append({
            "heading": "Outbreak Context",
            "heading_level": 2,
            "paragraphs": [
                f"The following samples from {region} have tested positive for "
                f"high-severity resistance gene(s) in the past 90 days, indicating "
                f"potential clonal spread or cross-facility transmission."
            ],
            "table": {
                "headers": ["Sample ID", "Date", "Facility", "Submitted By"],
                "rows": outbreak_table_rows,
            },
        })

    sections.append({
        "heading": f"Recommended Actions — {level} Protocol",
        "heading_level": 2,
        "bullet_list": RECOMMENDATIONS[level],
    })

    sections.append({
        "heading": "Technical Details",
        "heading_level": 2,
        "paragraphs": [
            f"Run ID: {alert.get('run_id')}",
            f"Analysis method: k-mer based genomic AMR screening (k=21, identity threshold ≥80%)",
            f"Database: WAT Genomics SQLite (wat_genomics.db)",
            f"Pipeline version: WAT Framework v1.0",
        ],
    })

    spec = {
        "output_path": output_path,
        "title": f"AMR Public Health Alert — {level} — {pathogen} — {region}",
        "sections": sections,
    }
    return build_document(spec)


def main():
    parser = argparse.ArgumentParser(description="Generate public health alert Word report")
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
        alert_file = spec.get("alert_file")
        output_path = spec.get("output_path", ".tmp/alert_report.docx")

        if alert_file:
            with open(alert_file) as f:
                alert = json.load(f)
        else:
            raise ValueError("'alert_file' is required (output of alert_score.py)")

        run_id = spec.get("run_id") or alert.get("run_id")
        if not run_id:
            raise ValueError("'run_id' is required")

        conn = get_conn(db_path)
        try:
            run_row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            run_info = dict(run_row) if run_row else {}
            amr_detail = get_run_amr_detail(conn, run_id)
            outbreak_ctx = get_outbreak_context(conn, alert)
        finally:
            conn.close()

        saved_path = build_alert_report(alert, amr_detail, outbreak_ctx,
                                        run_info, output_path)

        # Update report_path in alert_records
        conn2 = sqlite3.connect(db_path)
        try:
            conn2.execute(
                "UPDATE alert_records SET report_path=? WHERE run_id=?",
                (saved_path, run_id),
            )
            conn2.commit()
        finally:
            conn2.close()

        result = {
            "status": "ok",
            "output_path": saved_path,
            "alert_level": alert.get("alert_level"),
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
