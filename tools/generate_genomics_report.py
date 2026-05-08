"""
WAT tool: Compile all genomics analysis results into a Word document report.

Loads result files produced by qc_sequences.py, snp_detection.py,
amr_detection.py, and phylogenetics.py, then generates a structured Word doc.

Input JSON (--input or --input-file):
{
  "output_path": ".tmp/genomics_report.docx",
  "study_name": "My Bacterial WGS Study",
  "qc_file":    ".tmp/qc_report.json",        // optional
  "snp_file":   ".tmp/snp_results.json",      // optional
  "amr_file":   ".tmp/amr_results.json",      // optional
  "phylo_file": ".tmp/phylo/results.json"      // optional
}

Output JSON:
{
  "status": "ok",
  "output_path": ".tmp/genomics_report.docx"
}
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Import document builder from existing WAT tool
sys.path.insert(0, str(Path(__file__).parent))
from write_word_doc import build_document


def load_json(path: str) -> list | dict | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def format_large_number(n: int) -> str:
    return f"{n:,}"


def build_qc_section(qc_data: list) -> list:
    if not qc_data:
        return []

    headers = ["Sample", "Format", "Contigs", "Total Length (bp)", "N50 (bp)",
               "GC %", "N %", "QC Status"]
    rows = []
    for s in qc_data:
        status = "PASS" if s.get("pass_qc") else "FLAG: " + "; ".join(s.get("flags", []))
        if s.get("format") == "fasta":
            rows.append([
                s.get("sample_id", ""),
                "FASTA",
                format_large_number(s.get("contig_count", 0)),
                format_large_number(s.get("total_length", 0)),
                format_large_number(s.get("n50", 0)),
                f"{s.get('gc_content', 0):.1f}",
                f"{s.get('n_content', 0):.2f}",
                status,
            ])
        else:
            rows.append([
                s.get("sample_id", ""),
                "FASTQ",
                format_large_number(s.get("read_count", 0)) + " reads",
                format_large_number(s.get("total_bases", 0)),
                "-",
                f"{s.get('gc_content', 0):.1f}",
                "-",
                status,
            ])

    passed = sum(1 for s in qc_data if s.get("pass_qc"))
    return [
        {
            "heading": "Quality Control",
            "heading_level": 2,
            "paragraphs": [
                f"{len(qc_data)} samples analyzed. {passed} passed QC, "
                f"{len(qc_data) - passed} flagged for review."
            ],
            "table": {"headers": headers, "rows": rows},
        }
    ]


def build_snp_section(snp_data: list) -> list:
    if not snp_data:
        return []

    headers = ["Sample", "Total SNPs", "Total Indels"]
    rows = [[s.get("sample_id", ""),
             format_large_number(s.get("total_snps", 0)),
             format_large_number(s.get("total_indels", 0))]
            for s in snp_data]

    total_snps = sum(s.get("total_snps", 0) for s in snp_data)
    avg_snps = total_snps // len(snp_data) if snp_data else 0

    # Top-SNP samples detail (up to 3 samples shown)
    detail_paragraphs = []
    for sample in sorted(snp_data, key=lambda x: x.get("total_snps", 0), reverse=True)[:3]:
        top_snps = sample.get("snps", [])[:10]
        if top_snps:
            snp_str = ", ".join(
                f"pos {v['position']} {v['ref_allele']}→{v['alt_allele']}"
                for v in top_snps
            )
            detail_paragraphs.append(
                f"{sample['sample_id']} — first 10 SNPs: {snp_str}"
            )

    return [
        {
            "heading": "SNP Detection",
            "heading_level": 2,
            "paragraphs": [
                f"SNPs called against reference genome. "
                f"Total SNPs across all samples: {format_large_number(total_snps)}. "
                f"Average per sample: {format_large_number(avg_snps)}.",
            ] + detail_paragraphs,
            "table": {"headers": headers, "rows": rows},
        }
    ]


def build_amr_section(amr_data: list) -> list:
    if not amr_data:
        return []

    headers = ["Sample", "Genes Found", "Resistance Classes"]
    rows = [[s.get("sample_id", ""),
             str(s.get("hits_found", 0)),
             ", ".join(s.get("resistance_classes", []) or ["None"])]
            for s in amr_data]

    # Detailed hit table for samples with hits
    detail_sections = []
    for sample in amr_data:
        hits = sample.get("hits", [])
        if hits:
            hit_rows = [[h["gene"], h["drug_class"], f"{h['identity']*100:.1f}%",
                         format_large_number(h.get("gene_length", 0))]
                        for h in hits]
            detail_sections.append({
                "heading": f"AMR Detail: {sample['sample_id']}",
                "heading_level": 3,
                "table": {
                    "headers": ["Gene", "Drug Class", "k-mer Identity", "Gene Length (bp)"],
                    "rows": hit_rows,
                },
            })

    any_resistance = sum(1 for s in amr_data if s.get("hits_found", 0) > 0)
    return [
        {
            "heading": "Antimicrobial Resistance (AMR)",
            "heading_level": 2,
            "paragraphs": [
                f"{len(amr_data)} genomes screened. "
                f"{any_resistance} carry at least one detected AMR gene. "
                f"Identity threshold: 80% k-mer similarity (k=21)."
            ],
            "table": {"headers": headers, "rows": rows},
        }
    ] + detail_sections


def build_phylo_section(phylo_data: dict) -> list:
    if not phylo_data:
        return []

    samples = phylo_data.get("samples", [])
    method = phylo_data.get("tree_method", "nj").upper()
    k = phylo_data.get("kmer_size", 21)
    ascii_tree = phylo_data.get("ascii_tree", "")
    newick = phylo_data.get("newick", "")

    # Build distance matrix table (up to 10 samples)
    dm = phylo_data.get("distance_matrix", {})
    dist_headers = ["Sample"] + samples[:10]
    dist_rows = []
    for s in samples[:10]:
        row = [s]
        for t in samples[:10]:
            d = dm.get(s, {}).get(t, "-")
            row.append(f"{d:.4f}" if isinstance(d, float) else str(d))
        dist_rows.append(row)

    paragraphs = [
        f"{len(samples)} genomes included. Tree method: {method}. k-mer size: k={k}.",
        f"Newick tree: {newick}",
    ]
    if ascii_tree:
        paragraphs.append("ASCII tree:\n" + ascii_tree)

    sections = [
        {
            "heading": "Phylogenetics",
            "heading_level": 2,
            "paragraphs": paragraphs,
        }
    ]
    if dist_rows:
        sections.append({
            "heading": "Pairwise Jaccard Distance Matrix",
            "heading_level": 3,
            "paragraphs": ["Lower values = more closely related (0 = identical k-mer content)."],
            "table": {"headers": dist_headers, "rows": dist_rows},
        })

    return sections


def main():
    parser = argparse.ArgumentParser(description="Generate genomics analysis Word report")
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

        study_name = spec.get("study_name", "Bacterial WGS Analysis Report")
        output_path = spec.get("output_path", ".tmp/genomics_report.docx")

        qc_data   = load_json(spec.get("qc_file"))
        snp_data  = load_json(spec.get("snp_file"))
        amr_data  = load_json(spec.get("amr_file"))
        phylo_data = load_json(spec.get("phylo_file"))

        # Build sections
        sections = []

        sections.append({
            "heading": "Overview",
            "heading_level": 2,
            "paragraphs": [
                f"Study: {study_name}",
                "This report was generated automatically by the WAT genomics pipeline. "
                "It covers quality control, SNP detection, antimicrobial resistance screening, "
                "and phylogenetic analysis of bacterial whole-genome sequencing (WGS) data.",
                "Methods: Biopython v1.8x; SNP calling via k-mer anchored chunked alignment; "
                "AMR detection via k-mer identity against NCBI-curated gene database (k=21, ≥80%); "
                "Phylogenetics via Jaccard distance matrix and Neighbor-Joining tree construction.",
            ],
        })

        sections += build_qc_section(qc_data or [])
        sections += build_snp_section(snp_data or [])
        sections += build_amr_section(amr_data or [])
        sections += build_phylo_section(phylo_data or {})

        doc_spec = {
            "output_path": output_path,
            "title": study_name,
            "sections": sections,
        }

        saved_path = build_document(doc_spec)
        result = {"status": "ok", "output_path": saved_path}

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
