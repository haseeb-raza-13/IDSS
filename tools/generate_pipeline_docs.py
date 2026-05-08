"""
WAT tool: Generate a concise 2–3 page WAT Genomics Pipeline overview document.
Audience: policy makers, public health officials, journal reviewers.

Usage:
    python tools/generate_pipeline_docs.py
    python tools/generate_pipeline_docs.py --output path/to/output.docx
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_word_doc import build_document
from dotenv import load_dotenv

load_dotenv()

LOGO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "brand_assets", "uaf-logo.png")
)
DEFAULT_OUTPUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".tmp", "WAT_Genomics_Pipeline_Documentation.docx")
)


def make_spec(output_path: str) -> dict:
    return {
        "output_path": output_path,
        "font_name": "Times New Roman",
        "heading_font_size": 14,
        "body_font_size": 12,
        "title": "WAT Genomics Pipeline\nOne-Health Antimicrobial Resistance Surveillance System",
        "sections": [

            # ── Logo + Author ──────────────────────────────────────────────
            {
                "image": {
                    "path": LOGO_PATH,
                    "width_inches": 1.7,
                    "align": "center"
                }
            },
            {
                "paragraphs": [
                    "Dr. M. Umar Zafar Khan",
                    "Institute of Microbiology, University of Agriculture Faisalabad",
                    "Subject Expert / Visiting Associate Professor",
                    "College of Animal Science, Hebei Normal University of Science and Technology, China",
                ],
                "paragraph_align": "center"
            },

            # ── Overview ───────────────────────────────────────────────────
            {
                "heading": "Overview",
                "heading_level": 2,
                "paragraphs": [
                    "Antimicrobial resistance (AMR) is one of the greatest threats to global public "
                    "health, food security, and sustainable development. Resistance genes do not "
                    "respect species boundaries — the same genes that make bacteria untreatable in "
                    "hospital patients are found in livestock, companion animals, river water, and "
                    "agricultural soil. Addressing this threat requires integrated, cross-sector "
                    "surveillance that connects human, animal, and environmental data into a single "
                    "actionable picture. This is the mission of the WAT Genomics Pipeline.",

                    "The WAT (Workflows – Agents – Tools) Pipeline is a fully automated, "
                    "end-to-end surveillance platform built on the One-Health framework. It "
                    "ingests both DNA sequence data from bacterial whole-genome sequencing (WGS) "
                    "and conventional laboratory susceptibility test results, analyzes them through "
                    "five integrated processing phases, and delivers evidence-based intelligence to "
                    "public health professionals, epidemiologists, and policy makers in real time. "
                    "The entire system runs in pure Python with no requirement for specialized "
                    "bioinformatics software installations, making it deployable in resource-limited "
                    "settings across Pakistan and beyond.",
                ]
            },

            # ── Pipeline Flowchart ─────────────────────────────────────────
            {
                "heading": "How the Pipeline Works",
                "heading_level": 2,
                "paragraphs": [
                    "Data enters through two complementary streams — genomic sequences and "
                    "laboratory test results — flows through five processing phases, and exits as "
                    "policy-ready intelligence:"
                ],
                "flowchart": [
                    {
                        "box": (
                            "INPUT DATA\n"
                            "Bacterial DNA Sequences (FASTA/FASTQ from WGS)     "
                            "Laboratory Susceptibility Test Results (CSV/Excel)"
                        ),
                        "color": "1F3864",
                        "text_color": "FFFFFF",
                        "bold": True,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "PHASE 1 — GENOMIC ANALYSIS\n"
                            "Quality control of sequences  →  SNP mutation detection  →  "
                            "Resistance gene screening\n"
                            "Phylogenetic (evolutionary) analysis  →  Automated analysis report"
                        ),
                        "color": "D6E4F0",
                        "bold": False,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "PHASE 2 — PHENOTYPIC ANALYSIS\n"
                            "Process laboratory antibiotic susceptibility data\n"
                            "Classify isolates as MDR / XDR / PDR  →  Compute resistance rates  →  "
                            "Cross-validate with genomic findings"
                        ),
                        "color": "D5F5E3",
                        "bold": False,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "PHASE 3 — LONGITUDINAL DATABASE\n"
                            "Every run stored and tracked over time in a structured database\n"
                            "Query historical trends, compare regions, detect outbreak clusters"
                        ),
                        "color": "EBF5FB",
                        "bold": False,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "PHASE 4 — PUBLIC HEALTH ALERTING\n"
                            "Automated threat scoring:  LOW (Green)  →  MODERATE (Yellow)  →  "
                            "HIGH (Orange)  →  CRITICAL (Red)\n"
                            "Instant Word document alert brief  +  Live Google Sheets dashboard "
                            "shared with public health teams"
                        ),
                        "color": "FDEDEC",
                        "bold": False,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "PHASE 5 — AI PREDICTION & FORECASTING\n"
                            "Machine learning models predict antibiotic resistance for new samples\n"
                            "Time-series forecasting projects resistance trends 6 months ahead\n"
                            "Trained models backed up to Google Drive for cross-institutional sharing"
                        ),
                        "color": "FEF9E7",
                        "bold": False,
                    },
                    {"arrow": "↓"},
                    {
                        "box": (
                            "POLICY-READY OUTPUTS\n"
                            "Outbreak Alerts     Resistance Forecasts     ML Predictions\n"
                            "Epidemiological Reports     Real-Time Surveillance Dashboard"
                        ),
                        "color": "1F3864",
                        "text_color": "FFFFFF",
                        "bold": True,
                    },
                ]
            },

            # ── Phase Summary Table ────────────────────────────────────────
            {
                "heading": "What Each Phase Delivers",
                "heading_level": 2,
                "table": {
                    "headers": ["Phase", "What It Does", "Who Benefits"],
                    "rows": [
                        ["Genomic Analysis",
                         "Reads bacterial DNA to identify resistance genes, genetic mutations, "
                         "and evolutionary relationships between strains. Detects whether bacteria "
                         "carry genes for resistance before clinical symptoms appear.",
                         "Microbiologists, clinical laboratories, infection control teams"],

                        ["Phenotypic Analysis",
                         "Processes standard antibiotic susceptibility test results (disk "
                         "diffusion, E-test, MIC). Classifies each isolate as MDR, XDR, or PDR "
                         "and tracks resistance rates across regions and time periods.",
                         "Clinical microbiologists, hospital infection control officers"],

                        ["Longitudinal Database",
                         "Stores every analysis result permanently so resistance trends can be "
                         "tracked across months and years. Detects outbreak clusters when the "
                         "same resistance pattern appears in multiple locations within 90 days.",
                         "Epidemiologists, public health surveillance teams"],

                        ["Public Health Alerting",
                         "Automatically scores each new finding on a 0–100 threat scale and "
                         "assigns a color level. Generates a ready-to-send alert brief and "
                         "updates a live shared dashboard visible to all public health partners.",
                         "National health authorities, WHO/PAHO focal points, policy makers"],

                        ["AI Prediction & Forecasting",
                         "Trains machine learning models on accumulated data to predict "
                         "resistance outcomes for new patient samples. Projects resistance "
                         "rates 6 months into the future to support proactive treatment "
                         "guideline revision and antibiotic procurement planning.",
                         "Policy makers, pharmacies, antimicrobial stewardship committees"],
                    ]
                }
            },

            # ── Key Outputs ────────────────────────────────────────────────
            {
                "heading": "Key Policy Outputs",
                "heading_level": 2,
                "paragraphs": [
                    "The pipeline converts raw laboratory and genomic data directly into "
                    "decision-ready intelligence:"
                ],
                "bullet_list": [
                    "RED Alert — triggers immediate national AMR emergency response and WHO International "
                    "Health Regulations (IHR) notification",
                    "Outbreak signal — initiates epidemiological investigation, patient cohort "
                    "isolation, and inter-ward movement restrictions",
                    "Rising resistance forecast — prompts revision of empirical treatment guidelines "
                    "and antimicrobial stewardship programmes",
                    "Animal / environment sharing same resistance gene as human cases — triggers "
                    "zoonotic transmission investigation and restriction of antibiotic use in livestock",
                    "MDR rate exceeding 50% — informs reserve antibiotic access and stewardship policy",
                    "Genotype–phenotype concordance below 80% — flags need to review laboratory "
                    "diagnostic protocols and expand the resistance gene database",
                ]
            },

            # ── One-Health Framing ─────────────────────────────────────────
            {
                "heading": "One-Health Integration",
                "heading_level": 2,
                "paragraphs": [
                    "Every sample in the system is tagged by its source — human (clinical isolates), "
                    "animal (livestock, companion animals, wildlife), or environment (river water, "
                    "hospital drains, agricultural soil). This tagging makes it possible to see, "
                    "at a glance, whether the same resistance gene is circulating simultaneously "
                    "in a hospital ward, a poultry farm, and the irrigation canal downstream. "
                    "That cross-sector visibility is what enables genuinely coordinated One-Health "
                    "responses — the kind that WHO's Global Action Plan on AMR and Pakistan's "
                    "National Action Plan on AMR both call for, but which existing siloed "
                    "surveillance systems cannot provide.",
                ]
            },

            # ── Footer ────────────────────────────────────────────────────
            {
                "paragraphs": [
                    "─" * 80,
                    "WAT Genomics Pipeline  |  University of Agriculture Faisalabad  |  2026",
                    "Developed under the One-Health AMR Surveillance Initiative",
                ],
                "paragraph_align": "center"
            },
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Generate WAT Genomics Pipeline overview document")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output .docx path")
    args = parser.parse_args()

    spec = make_spec(args.output)
    saved = build_document(spec)
    print(json.dumps({"status": "ok", "output_path": saved}, indent=2))


if __name__ == "__main__":
    main()
