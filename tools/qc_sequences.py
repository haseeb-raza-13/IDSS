"""
WAT tool: Compute quality control metrics for bacterial genome assemblies (FASTA)
and raw reads (FASTQ).

Input JSON (--input or --input-file):
{
  "files": ["/path/genome1.fasta", "/path/reads1.fastq"],
  "output_file": ".tmp/qc_report.json"   // optional
}

Output JSON:
{
  "status": "ok",
  "qc_report": [
    {
      "sample_id": "genome1",
      "format": "fasta",
      "contig_count": 42,
      "total_length": 4521000,
      "n50": 250000,
      "gc_content": 65.3,
      "n_content": 0.05,
      "largest_contig": 800000,
      "flags": ["WARNING: high N content"]
    }
  ],
  "output_file": ".tmp/qc_report.json"
}
"""

import argparse
import json
import os
import sys
from pathlib import Path

from Bio import SeqIO
from dotenv import load_dotenv

load_dotenv()

FASTA_EXTS = {".fasta", ".fa", ".fna"}
FASTQ_EXTS = {".fastq", ".fq"}


def compute_n50(lengths: list) -> int:
    if not lengths:
        return 0
    sorted_len = sorted(lengths, reverse=True)
    half = sum(sorted_len) / 2
    cumulative = 0
    for l in sorted_len:
        cumulative += l
        if cumulative >= half:
            return l
    return sorted_len[-1]


def qc_fasta(file_path: Path) -> dict:
    records = list(SeqIO.parse(file_path, "fasta"))
    if not records:
        raise ValueError("No sequences found in file")

    lengths = [len(r.seq) for r in records]
    all_seq = "".join(str(r.seq).upper() for r in records)
    total = len(all_seq)

    gc = (all_seq.count("G") + all_seq.count("C")) / total * 100
    n_pct = all_seq.count("N") / total * 100
    n50 = compute_n50(lengths)

    flags = []
    if gc < 30 or gc > 80:
        flags.append(f"WARNING: unusual GC content ({gc:.1f}%)")
    if n_pct > 5:
        flags.append(f"WARNING: high N content ({n_pct:.2f}%)")
    if total < 500_000:
        flags.append(f"WARNING: assembly shorter than 500 kb ({total:,} bp)")
    if total > 15_000_000:
        flags.append(f"WARNING: unusually large assembly ({total:,} bp)")
    if len(records) > 500:
        flags.append(f"WARNING: highly fragmented assembly ({len(records)} contigs)")

    return {
        "sample_id": file_path.stem,
        "file": str(file_path),
        "format": "fasta",
        "contig_count": len(records),
        "total_length": total,
        "n50": n50,
        "gc_content": round(gc, 2),
        "n_content": round(n_pct, 2),
        "largest_contig": max(lengths),
        "smallest_contig": min(lengths),
        "mean_contig_length": round(total / len(records), 1),
        "flags": flags,
        "pass_qc": len(flags) == 0,
    }


def qc_fastq(file_path: Path) -> dict:
    records = list(SeqIO.parse(file_path, "fastq"))
    if not records:
        raise ValueError("No reads found in file")

    lengths = [len(r.seq) for r in records]
    all_seq = "".join(str(r.seq).upper() for r in records)
    total_bases = sum(lengths)

    all_quals = []
    for r in records:
        all_quals.extend(r.letter_annotations.get("phred_quality", []))

    gc = (all_seq.count("G") + all_seq.count("C")) / len(all_seq) * 100 if all_seq else 0
    avg_q = sum(all_quals) / len(all_quals) if all_quals else 0

    q30_count = sum(1 for q in all_quals if q >= 30)
    q30_pct = q30_count / len(all_quals) * 100 if all_quals else 0

    flags = []
    if avg_q < 20:
        flags.append(f"WARNING: low average quality ({avg_q:.1f})")
    if q30_pct < 70:
        flags.append(f"WARNING: Q30 bases only {q30_pct:.1f}%")
    if gc < 30 or gc > 80:
        flags.append(f"WARNING: unusual GC content ({gc:.1f}%)")

    return {
        "sample_id": file_path.stem,
        "file": str(file_path),
        "format": "fastq",
        "read_count": len(records),
        "total_bases": total_bases,
        "avg_read_length": round(sum(lengths) / len(lengths), 1),
        "min_read_length": min(lengths),
        "max_read_length": max(lengths),
        "gc_content": round(gc, 2),
        "avg_quality": round(avg_q, 2),
        "q30_percent": round(q30_pct, 2),
        "flags": flags,
        "pass_qc": len(flags) == 0,
    }


def main():
    parser = argparse.ArgumentParser(description="QC metrics for genomic sequence files")
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

        files = spec.get("files", [])
        if not files:
            raise ValueError("'files' list is required and must not be empty")

        qc_results = []
        errors = []

        for file_str in files:
            file_path = Path(file_str)
            if not file_path.exists():
                errors.append({"file": file_str, "error": "File not found"})
                continue
            try:
                ext = file_path.suffix.lower()
                if ext in FASTA_EXTS:
                    result = qc_fasta(file_path)
                elif ext in FASTQ_EXTS:
                    result = qc_fastq(file_path)
                else:
                    errors.append({"file": file_str, "error": f"Unsupported extension: {ext}"})
                    continue
                qc_results.append(result)
            except Exception as e:
                errors.append({"file": file_str, "error": str(e)})

        passed = sum(1 for r in qc_results if r.get("pass_qc"))
        output_file = spec.get("output_file", ".tmp/qc_report.json")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(qc_results, f, indent=2)

        result = {
            "status": "ok",
            "samples_analyzed": len(qc_results),
            "samples_passed": passed,
            "samples_flagged": len(qc_results) - passed,
            "qc_report": qc_results,
            "output_file": output_file,
        }
        if errors:
            result["errors"] = errors

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
