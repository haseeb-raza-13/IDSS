"""
WAT tool: Build a phylogenetic tree from bacterial genome assemblies using
k-mer Jaccard distances and Neighbor-Joining (or UPGMA) tree construction.

k-mer Jaccard distance:
  D(A, B) = 1 - |kmers(A) ∩ kmers(B)| / |kmers(A) ∪ kmers(B)|

This is equivalent to Mash distance for population-level analysis and requires
no multiple sequence alignment. Recommended k=21 for whole bacterial genomes.

Input JSON (--input or --input-file):
{
  "files": ["/path/genome1.fasta", "/path/genome2.fasta"],
  "output_dir": ".tmp/phylo",       // optional
  "tree_method": "nj",              // "nj" (default) or "upgma"
  "kmer_size": 21                   // optional, default 21
}

Output JSON:
{
  "status": "ok",
  "sample_count": 5,
  "tree_method": "nj",
  "newick": "(sample1:0.01,sample2:0.02,...);",
  "distance_matrix": {...},
  "ascii_tree": "...",
  "output_dir": ".tmp/phylo"
}
"""

import argparse
import json
import os
import sys
from io import StringIO
from pathlib import Path

from Bio import SeqIO
from Bio.Phylo.TreeConstruction import DistanceMatrix, DistanceTreeConstructor
from Bio import Phylo
from dotenv import load_dotenv

load_dotenv()

DEFAULT_K = 21


def build_kmer_set(seq: str, k: int) -> set:
    seq = seq.upper()
    return {seq[i:i+k] for i in range(len(seq) - k + 1) if "N" not in seq[i:i+k]}


def jaccard_distance(set_a: set, set_b: set) -> float:
    union = set_a | set_b
    if not union:
        return 0.0
    intersection = set_a & set_b
    return 1.0 - len(intersection) / len(union)


def load_genome_kmers(file_path: Path, k: int) -> tuple:
    """Return (sample_id, kmer_set) from all contigs in a FASTA file."""
    all_seq = ""
    for record in SeqIO.parse(file_path, "fasta"):
        all_seq += str(record.seq)
    if not all_seq:
        raise ValueError(f"No sequence data in {file_path}")
    return file_path.stem, build_kmer_set(all_seq, k)


def build_distance_matrix(samples: list) -> DistanceMatrix:
    """
    Build a lower-triangular DistanceMatrix from (name, kmer_set) pairs.
    Biopython's DistanceMatrix expects the diagonal to be 0 and the lower triangle
    filled row by row.
    """
    names = [s[0] for s in samples]
    n = len(names)

    # Lower-triangular matrix (including diagonal of 0)
    matrix = []
    for i in range(n):
        row = []
        for j in range(i + 1):
            if i == j:
                row.append(0.0)
            else:
                d = jaccard_distance(samples[i][1], samples[j][1])
                row.append(round(d, 6))
        matrix.append(row)

    return DistanceMatrix(names, matrix)


def tree_to_newick(tree) -> str:
    buf = StringIO()
    Phylo.write(tree, buf, "newick")
    return buf.getvalue().strip()


def tree_to_ascii(tree) -> str:
    buf = StringIO()
    Phylo.draw_ascii(tree, file=buf)
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Build phylogenetic tree from genome assemblies")
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
        if len(files) < 3:
            raise ValueError("Phylogenetic analysis requires at least 3 genomes")

        k = spec.get("kmer_size", DEFAULT_K)
        method = spec.get("tree_method", "nj").lower()
        if method not in ("nj", "upgma"):
            raise ValueError("tree_method must be 'nj' or 'upgma'")

        output_dir = Path(spec.get("output_dir", ".tmp/phylo"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load genomes and build k-mer sets
        samples = []
        errors = []
        for file_str in files:
            file_path = Path(file_str)
            if not file_path.exists():
                errors.append({"file": file_str, "error": "File not found"})
                continue
            try:
                print(f"  Building k-mer set: {file_path.name}", file=sys.stderr)
                sample_id, kmer_set = load_genome_kmers(file_path, k)
                samples.append((sample_id, kmer_set))
            except Exception as e:
                errors.append({"file": file_str, "error": str(e)})

        if len(samples) < 3:
            raise ValueError(
                f"Need at least 3 valid genomes; only {len(samples)} loaded successfully"
            )

        # Build pairwise distance matrix
        print(f"  Computing {len(samples)}x{len(samples)} distance matrix ...", file=sys.stderr)
        dm = build_distance_matrix(samples)

        # Build distance dict for output
        dist_dict = {}
        for i, (name_i, _) in enumerate(samples):
            dist_dict[name_i] = {}
            for j, (name_j, _) in enumerate(samples):
                if i == j:
                    dist_dict[name_i][name_j] = 0.0
                elif i > j:
                    dist_dict[name_i][name_j] = dm[name_i, name_j]
                else:
                    dist_dict[name_i][name_j] = dm[name_j, name_i]

        # Construct tree
        constructor = DistanceTreeConstructor()
        if method == "nj":
            tree = constructor.nj(dm)
        else:
            tree = constructor.upgma(dm)

        # Export outputs
        newick_str = tree_to_newick(tree)
        ascii_str = tree_to_ascii(tree)

        newick_file = output_dir / "tree.nwk"
        with open(newick_file, "w") as f:
            f.write(newick_str)

        ascii_file = output_dir / "tree_ascii.txt"
        with open(ascii_file, "w") as f:
            f.write(ascii_str)

        phylo_result = {
            "sample_count": len(samples),
            "samples": [s[0] for s in samples],
            "kmer_size": k,
            "tree_method": method,
            "newick": newick_str,
            "distance_matrix": dist_dict,
            "ascii_tree": ascii_str,
            "newick_file": str(newick_file),
        }

        results_file = output_dir / "results.json"
        with open(results_file, "w") as f:
            json.dump(phylo_result, f, indent=2)

        result = {
            "status": "ok",
            **phylo_result,
            "output_dir": str(output_dir),
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
