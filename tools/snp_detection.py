"""
WAT tool: Detect SNPs in bacterial genome assemblies relative to a reference genome.

Uses a k-mer anchored chunked alignment strategy:
  1. Divide reference into 50 kb windows
  2. Anchor each window in the query using a 21-mer seed
  3. Align ref/query windows with Biopython PairwiseAligner (local mode)
  4. Extract mismatches as SNPs

Works best with high-identity sequences (>90% ANI). Indels are also reported
but SNP positions are 1-based in reference coordinates.

Input JSON (--input or --input-file):
{
  "query_files": ["/path/sample1.fasta", "/path/sample2.fasta"],
  "reference_file": "/path/reference.fasta",
  "output_file": ".tmp/snp_results.json",   // optional
  "chunk_size": 50000,                       // optional, default 50000
  "seed_k": 21                               // optional, default 21
}

Output JSON:
{
  "status": "ok",
  "reference": "ref_id",
  "samples": [
    {
      "sample_id": "sample1",
      "total_snps": 42,
      "total_indels": 3,
      "snps": [
        {"position": 12345, "ref_allele": "A", "alt_allele": "G", "type": "SNP"}
      ]
    }
  ],
  "output_file": ".tmp/snp_results.json"
}
"""

import argparse
import json
import os
import sys
from pathlib import Path

from Bio import SeqIO
from Bio.Align import PairwiseAligner
from dotenv import load_dotenv

load_dotenv()

CHUNK_SIZE = 50_000
SEED_K = 21


def load_reference(ref_file: Path) -> tuple:
    """Return (accession, concatenated_sequence_string)."""
    records = list(SeqIO.parse(ref_file, "fasta"))
    if not records:
        raise ValueError(f"No sequences in reference file: {ref_file}")
    # Concatenate all contigs with a separator of 'N' * 100
    sep = "N" * 100
    ref_seq = sep.join(str(r.seq).upper() for r in records)
    ref_id = records[0].id
    return ref_id, ref_seq


def load_query(query_file: Path) -> tuple:
    """Return (sample_id, concatenated_sequence_string)."""
    records = list(SeqIO.parse(query_file, "fasta"))
    if not records:
        raise ValueError(f"No sequences in query file: {query_file}")
    sep = "N" * 100
    seq = sep.join(str(r.seq).upper() for r in records)
    return query_file.stem, seq


def make_aligner() -> PairwiseAligner:
    aligner = PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -0.5
    return aligner


def extract_snps_from_alignment(alignment, ref_chunk_start: int) -> list:
    """
    Parse a Biopython Alignment object and return a list of SNP/indel dicts.
    ref_chunk_start: offset of this chunk in the full reference (0-based).
    """
    variants = []
    # alignment.aligned = (target_blocks, query_blocks)
    # Each block is an array of [start, end] coordinate pairs
    target_blocks = alignment.aligned[0]
    query_blocks = alignment.aligned[1]

    for (ts, te), (qs, qe) in zip(target_blocks, query_blocks):
        ref_sub = str(alignment.target[ts:te]).upper()
        qry_sub = str(alignment.query[qs:qe]).upper()

        block_len = min(len(ref_sub), len(qry_sub))
        for i in range(block_len):
            r, q = ref_sub[i], qry_sub[i]
            if r != q and r != "N" and q != "N":
                variants.append({
                    "position": ref_chunk_start + ts + i + 1,  # 1-based
                    "ref_allele": r,
                    "alt_allele": q,
                    "type": "SNP",
                })

        # Indel: size difference between ref and query blocks
        if len(ref_sub) != len(qry_sub):
            diff = len(ref_sub) - len(qry_sub)
            if diff > 0:
                variants.append({
                    "position": ref_chunk_start + ts + block_len + 1,
                    "type": "DELETION",
                    "length": diff,
                })
            else:
                variants.append({
                    "position": ref_chunk_start + ts + block_len + 1,
                    "type": "INSERTION",
                    "length": abs(diff),
                })

    return variants


def find_anchor_in_query(seed: str, query_str: str) -> int:
    """Return position of seed in query, or -1 if not found."""
    return query_str.find(seed)


def call_variants(ref_seq: str, query_seq: str,
                  chunk_size: int = CHUNK_SIZE, seed_k: int = SEED_K) -> list:
    aligner = make_aligner()
    variants = []
    seen_positions = set()

    for chunk_start in range(0, len(ref_seq), chunk_size):
        chunk_end = min(chunk_start + chunk_size, len(ref_seq))
        ref_chunk = ref_seq[chunk_start:chunk_end]

        # Skip chunks that are mostly Ns (separator regions)
        if ref_chunk.count("N") / len(ref_chunk) > 0.5:
            continue

        # Find a clean seed from the middle of the chunk
        mid = len(ref_chunk) // 2
        seed = None
        for offset in range(0, len(ref_chunk) - seed_k, 500):
            candidate = ref_chunk[mid - offset: mid - offset + seed_k]
            if "N" not in candidate:
                seed = candidate
                break
            candidate = ref_chunk[mid + offset: mid + offset + seed_k]
            if "N" not in candidate:
                seed = candidate
                break

        if seed is None:
            continue

        query_anchor = find_anchor_in_query(seed, query_seq)
        if query_anchor == -1:
            continue

        # Estimate query window from anchor
        anchor_offset = ref_chunk.index(seed)
        q_start = max(0, query_anchor - anchor_offset - 1000)
        q_end = min(len(query_seq), q_start + chunk_size + 2000)
        query_chunk = query_seq[q_start:q_end]

        try:
            alignments = aligner.align(ref_chunk, query_chunk)
            best = next(iter(alignments), None)
            if best is None:
                continue

            chunk_variants = extract_snps_from_alignment(best, chunk_start)

            for v in chunk_variants:
                pos = v["position"]
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    variants.append(v)
        except Exception:
            continue

    return sorted(variants, key=lambda x: x["position"])


def main():
    parser = argparse.ArgumentParser(description="Call SNPs vs. reference genome")
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

        ref_file = Path(spec["reference_file"])
        if not ref_file.exists():
            raise FileNotFoundError(f"Reference file not found: {ref_file}")

        chunk_size = spec.get("chunk_size", CHUNK_SIZE)
        seed_k = spec.get("seed_k", SEED_K)

        print(f"  Loading reference: {ref_file.name}", file=sys.stderr)
        ref_id, ref_seq = load_reference(ref_file)

        samples_results = []
        errors = []

        for query_str in spec.get("query_files", []):
            query_file = Path(query_str)
            if not query_file.exists():
                errors.append({"file": query_str, "error": "File not found"})
                continue
            try:
                sample_id, query_seq = load_query(query_file)
                print(f"  Processing {sample_id} ...", file=sys.stderr)

                variants = call_variants(ref_seq, query_seq, chunk_size, seed_k)
                snps = [v for v in variants if v["type"] == "SNP"]
                indels = [v for v in variants if v["type"] in ("INSERTION", "DELETION")]

                samples_results.append({
                    "sample_id": sample_id,
                    "file": str(query_file),
                    "total_snps": len(snps),
                    "total_indels": len(indels),
                    "snps": snps,
                    "indels": indels,
                })
            except Exception as e:
                errors.append({"file": query_str, "error": str(e)})

        output_file = spec.get("output_file", ".tmp/snp_results.json")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(samples_results, f, indent=2)

        result = {
            "status": "ok",
            "reference": ref_id,
            "reference_length": len(ref_seq),
            "samples": [
                {
                    "sample_id": s["sample_id"],
                    "total_snps": s["total_snps"],
                    "total_indels": s["total_indels"],
                }
                for s in samples_results
            ],
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
