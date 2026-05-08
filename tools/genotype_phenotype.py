"""
WAT tool: Build a genotype–phenotype concordance table.

For samples that have both genomic AMR hits (from amr_detection.py stored via
db_store_run.py) and phenotypic AST records (stored via phenotypic_analysis.py),
this tool produces a concordance matrix showing where genomic predictions match
the laboratory phenotype — and flags discordant cases for follow-up.

Concordance logic per sample × drug class:
  Genomic prediction = Resistant if any AMR hit exists for that drug class
  Phenotypic result  = R (resistant) from AST records
  Concordant if both agree; discordant if they disagree.
  Interpretation 'I' is treated as S for concordance but flagged separately.

Requires at least one genomic run AND at least one phenotypic run sharing sample IDs.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "uuid-of-genomic-run",    // filter to a specific run (optional)
  "output_file": ".tmp/geno_pheno_concordance.json"
}

Output JSON:
{
  "status": "ok",
  "matched_samples": 18,
  "concordance_rate_percent": 90.0,
  "concordance_table": [...],
  "discordant_cases": [...],
  "intermediate_phenotype_cases": [...],
  "output_file": "..."
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

# Drug class → list of representative antibiotics for phenotypic lookup
CLASS_TO_ANTIBIOTICS = {
    "Beta-lactam":    ["Ampicillin", "Amoxicillin", "Piperacillin"],
    "Cephalosporin":  ["Ceftriaxone", "Cefotaxime", "Ceftazidime", "Cefepime"],
    "Carbapenem":     ["Meropenem", "Imipenem", "Ertapenem", "Doripenem"],
    "Monobactam":     ["Aztreonam"],
    "Quinolone":      ["Ciprofloxacin", "Levofloxacin", "Moxifloxacin"],
    "Aminoglycoside": ["Gentamicin", "Amikacin", "Tobramycin"],
    "Tetracycline":   ["Tetracycline", "Doxycycline", "Tigecycline"],
    "Macrolide":      ["Erythromycin", "Azithromycin", "Clindamycin"],
    "Glycopeptide":   ["Vancomycin", "Teicoplanin"],
    "Oxazolidinone":  ["Linezolid"],
    "Sulfonamide":    ["Trimethoprim-Sulfamethoxazole", "Trimethoprim"],
    "Polymyxin":      ["Colistin", "Polymyxin B"],
    "Phenicol":       ["Chloramphenicol"],
    "Rifamycin":      ["Rifampicin", "Rifampin"],
    "Nitrofuran":     ["Nitrofurantoin"],
    "Fosfomycin":     ["Fosfomycin"],
    "Lipopeptide":    ["Daptomycin"],
}

ANTIBIOTIC_TO_CLASS = {}
for cls, abx_list in CLASS_TO_ANTIBIOTICS.items():
    for abx in abx_list:
        ANTIBIOTIC_TO_CLASS[abx] = cls


def get_conn(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_genomic_amr(conn, run_id=None) -> dict:
    """Return {sample_id: set(drug_classes_with_hits)}."""
    params = []
    where = ""
    if run_id:
        where = "WHERE ar.run_id = ?"
        params.append(run_id)

    rows = conn.execute(
        f"""SELECT s.sample_id, ah.drug_class
            FROM amr_hits ah
            JOIN amr_results ar ON ah.amr_pk = ar.amr_pk
            JOIN samples s ON ar.sample_pk = s.sample_pk
            {where}""",
        params,
    ).fetchall()

    genomic = {}
    for row in rows:
        sid = row["sample_id"]
        cls = row["drug_class"] or "Unknown"
        genomic.setdefault(sid, set()).add(cls)
    return genomic


def fetch_phenotypic_ast(conn) -> dict:
    """Return {sample_id: {drug_class: interpretation}} using worst interpretation per class."""
    rows = conn.execute(
        """SELECT ps.sample_id, ar.antibiotic, ar.interpretation
           FROM ast_records ar
           JOIN phenotypic_samples ps ON ar.pheno_sample_pk = ps.pheno_sample_pk"""
    ).fetchall()

    pheno = {}
    interp_rank = {"S": 0, "I": 1, "R": 2}
    for row in rows:
        sid = row["sample_id"]
        abx = row["antibiotic"]
        interp = (row["interpretation"] or "").upper()
        drug_class = ANTIBIOTIC_TO_CLASS.get(abx, "Other")
        if drug_class == "Other":
            continue
        current = pheno.setdefault(sid, {}).get(drug_class)
        if current is None or interp_rank.get(interp, 0) > interp_rank.get(current, 0):
            pheno[sid][drug_class] = interp
    return pheno


def build_concordance(genomic: dict, phenotypic: dict) -> tuple:
    concordant = []
    discordant = []
    intermediate = []

    matched_sample_ids = set(genomic.keys()) & set(phenotypic.keys())

    for sid in sorted(matched_sample_ids):
        geno_classes = genomic[sid]
        pheno_classes = phenotypic[sid]
        all_classes = geno_classes | set(pheno_classes.keys())

        for drug_class in sorted(all_classes):
            geno_resistant = drug_class in geno_classes
            pheno_interp = pheno_classes.get(drug_class)

            if pheno_interp is None:
                continue  # no phenotypic data for this class

            pheno_resistant = pheno_interp == "R"
            pheno_intermediate = pheno_interp == "I"

            entry = {
                "sample_id": sid,
                "drug_class": drug_class,
                "genomic_genes_present": geno_resistant,
                "genomic_prediction": "Resistant" if geno_resistant else "Susceptible",
                "phenotypic_interpretation": pheno_interp,
                "concordant": geno_resistant == pheno_resistant,
            }

            if pheno_intermediate:
                entry["note"] = "Intermediate phenotype — excluded from concordance rate"
                intermediate.append(entry)
            elif entry["concordant"]:
                concordant.append(entry)
            else:
                entry["discordance_type"] = (
                    "False_Positive_Genomic"  # gene present but phenotype S
                    if geno_resistant else
                    "False_Negative_Genomic"  # gene absent but phenotype R
                )
                discordant.append(entry)

    all_pairs = concordant + discordant
    rate = round(len(concordant) / len(all_pairs) * 100, 1) if all_pairs else 0.0

    return matched_sample_ids, concordant, discordant, intermediate, rate


def main():
    parser = argparse.ArgumentParser(description="Genotype–phenotype concordance analysis")
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

        conn = get_conn(db_path)
        try:
            genomic = fetch_genomic_amr(conn, run_id)
            phenotypic = fetch_phenotypic_ast(conn)
        finally:
            conn.close()

        if not genomic:
            raise ValueError("No genomic AMR data found in database. Run the genomic pipeline first.")
        if not phenotypic:
            raise ValueError("No phenotypic AST data found. Run phenotypic_analysis.py first.")

        matched_ids, concordant, discordant, intermediate, rate = build_concordance(
            genomic, phenotypic
        )

        all_concordance = concordant + discordant
        result = {
            "status": "ok",
            "matched_samples": len(matched_ids),
            "total_class_pairs": len(all_concordance),
            "concordant_pairs": len(concordant),
            "discordant_pairs": len(discordant),
            "intermediate_pairs": len(intermediate),
            "concordance_rate_percent": rate,
            "concordance_table": all_concordance,
            "discordant_cases": discordant,
            "intermediate_phenotype_cases": intermediate,
        }

        output_file = spec.get("output_file", ".tmp/geno_pheno_concordance.json")
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
