"""
WAT tool: Catalog local FASTA/FASTQ sequence files and extract basic metadata.

Input JSON (--input or --input-file):
{
  "directory": "/path/to/sequences",
  "extensions": [".fasta", ".fa", ".fna", ".fastq", ".fq"]   // optional
}

Output JSON:
{
  "status": "ok",
  "sample_count": 5,
  "samples": [
    {
      "sample_id": "sample1",
      "file": "/abs/path/sample1.fasta",
      "format": "fasta",
      "contig_count": 1,
      "total_length": 4500000,
      "gc_content": 65.2,
      "n_content": 0.1
    }
  ],
  "index_file": ".tmp/sequences_index.json"
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

DEFAULT_EXTENSIONS = [".fasta", ".fa", ".fna", ".fastq", ".fq"]


def gc_content(seq: str) -> float:
    seq = seq.upper()
    gc = seq.count("G") + seq.count("C")
    return round(gc / len(seq) * 100, 2) if seq else 0.0


def n_content(seq: str) -> float:
    return round(seq.upper().count("N") / len(seq) * 100, 2) if seq else 0.0


def avg_quality(records) -> float:
    total, count = 0, 0
    for r in records:
        quals = r.letter_annotations.get("phred_quality", [])
        total += sum(quals)
        count += len(quals)
    return round(total / count, 2) if count else 0.0


def catalog_file(file_path: Path) -> dict:
    ext = file_path.suffix.lower()
    fmt = "fastq" if ext in (".fastq", ".fq") else "fasta"

    records = list(SeqIO.parse(file_path, fmt))
    if not records:
        return None

    if fmt == "fasta":
        lengths = [len(r.seq) for r in records]
        all_seq = "".join(str(r.seq) for r in records)
        info = {
            "sample_id": file_path.stem,
            "file": str(file_path.resolve()),
            "format": fmt,
            "contig_count": len(records),
            "total_length": sum(lengths),
            "largest_contig": max(lengths),
            "smallest_contig": min(lengths),
            "gc_content": gc_content(all_seq),
            "n_content": n_content(all_seq),
            "n50": compute_n50(lengths),
        }
    else:
        lengths = [len(r.seq) for r in records]
        all_seq = "".join(str(r.seq) for r in records)
        info = {
            "sample_id": file_path.stem,
            "file": str(file_path.resolve()),
            "format": fmt,
            "read_count": len(records),
            "total_bases": sum(lengths),
            "avg_read_length": round(sum(lengths) / len(lengths), 1),
            "gc_content": gc_content(all_seq),
            "avg_quality": avg_quality(records),
        }

    return info


def compute_n50(lengths: list) -> int:
    if not lengths:
        return 0
    sorted_lengths = sorted(lengths, reverse=True)
    total = sum(sorted_lengths)
    cumulative = 0
    for length in sorted_lengths:
        cumulative += length
        if cumulative >= total / 2:
            return length
    return sorted_lengths[-1]


def main():
    parser = argparse.ArgumentParser(description="Catalog local FASTA/FASTQ files")
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

        directory = Path(spec["directory"])
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        extensions = spec.get("extensions", DEFAULT_EXTENSIONS)
        samples = []
        errors = []

        for ext in extensions:
            for file_path in sorted(directory.glob(f"*{ext}")):
                try:
                    info = catalog_file(file_path)
                    if info:
                        samples.append(info)
                except Exception as e:
                    errors.append({"file": str(file_path), "error": str(e)})

        os.makedirs(".tmp", exist_ok=True)
        index_file = ".tmp/sequences_index.json"
        with open(index_file, "w") as f:
            json.dump(samples, f, indent=2)

        result = {
            "status": "ok",
            "sample_count": len(samples),
            "samples": samples,
            "index_file": index_file,
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
