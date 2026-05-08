"""
WAT tool: Detect antimicrobial resistance (AMR) genes in bacterial genome assemblies.

Strategy:
  1. On first run, fetch a curated AMR gene reference database from NCBI and
     cache it at .tmp/amr_db.fasta (skipped on subsequent runs).
  2. Build a k-mer index (k=21) of the AMR database.
  3. For each query genome, compute k-mer identity against every AMR gene.
  4. Report hits where k-mer identity >= identity_threshold (default 0.80).

Covered resistance classes: beta-lactams, carbapenems, methicillin, glycopeptides,
tetracyclines, sulfonamides, aminoglycosides, quinolones, macrolides, colistin.

Requires NCBI_EMAIL in .env for the initial database download.

Input JSON (--input or --input-file):
{
  "query_files": ["/path/genome1.fasta"],
  "output_file": ".tmp/amr_results.json",      // optional
  "identity_threshold": 0.80,                   // optional, default 0.80
  "amr_db": "/path/custom_amr_db.fasta"         // optional: skip NCBI fetch
}

Output JSON:
{
  "status": "ok",
  "samples": [
    {
      "sample_id": "genome1",
      "hits": [
        {
          "gene": "blaNDM-1",
          "drug_class": "Carbapenem",
          "identity": 0.95,
          "gene_length": 813
        }
      ]
    }
  ],
  "output_file": ".tmp/amr_results.json"
}
"""

import argparse
import json
import os
import sys
import time
from io import StringIO
from pathlib import Path

from Bio import Entrez, SeqIO
from dotenv import load_dotenv

load_dotenv()

Entrez.email = os.getenv("NCBI_EMAIL", "anonymous@example.com")
api_key = os.getenv("NCBI_API_KEY", "")
if api_key:
    Entrez.api_key = api_key

RATE_DELAY = 0.11 if api_key else 0.34

DEFAULT_DB_PATH = ".tmp/amr_db.fasta"
KMER_SIZE = 21
DEFAULT_IDENTITY = 0.80

# Curated list: (gene_name, drug_class, search_term_for_NCBI)
AMR_GENE_QUERIES = [
    ("blaTEM-1",   "Beta-lactam",   "blaTEM-1[Gene Name] Escherichia coli[Organism]"),
    ("blaSHV-1",   "Beta-lactam",   "blaSHV[Gene Name] Klebsiella pneumoniae[Organism]"),
    ("blaCTX-M-15","ESBL",          "blaCTX-M-15[Gene Name]"),
    ("blaKPC-2",   "Carbapenem",    "blaKPC-2[Gene Name]"),
    ("blaNDM-1",   "Carbapenem",    "blaNDM-1[Gene Name]"),
    ("blaOXA-48",  "Carbapenem",    "blaOXA-48[Gene Name]"),
    ("mecA",       "Methicillin",   "mecA[Gene Name] Staphylococcus aureus[Organism]"),
    ("vanA",       "Glycopeptide",  "vanA[Gene Name] Enterococcus[Organism]"),
    ("vanB",       "Glycopeptide",  "vanB[Gene Name] Enterococcus[Organism]"),
    ("tetA",       "Tetracycline",  "tetA[Gene Name] transposon[Title]"),
    ("tetB",       "Tetracycline",  "tetB[Gene Name] transposon[Title]"),
    ("tetM",       "Tetracycline",  "tetM[Gene Name]"),
    ("sul1",       "Sulfonamide",   "sul1[Gene Name] integron[Title]"),
    ("sul2",       "Sulfonamide",   "sul2[Gene Name]"),
    ("aac(6')-Ib", "Aminoglycoside","aac(6')[Gene Name] Ib[Title]"),
    ("aph(3')-Ia", "Aminoglycoside","aph(3')[Gene Name] Ia[Title]"),
    ("qnrS1",      "Quinolone",     "qnrS1[Gene Name]"),
    ("qnrB1",      "Quinolone",     "qnrB1[Gene Name]"),
    ("ermB",       "Macrolide",     "ermB[Gene Name]"),
    ("ermA",       "Macrolide",     "ermA[Gene Name] Streptococcus[Organism]"),
    ("mcr-1",      "Colistin",      "mcr-1[Gene Name]"),
    ("cfr",        "Phenicol/Oxazolidinone", "cfr[Gene Name] plasmid[Title]"),
]


def fetch_amr_database(db_path: Path) -> int:
    """Download one representative sequence per AMR gene from NCBI. Returns count."""
    records_written = 0
    with open(db_path, "w") as out_f:
        for gene_name, drug_class, query in AMR_GENE_QUERIES:
            try:
                handle = Entrez.esearch(db="nucleotide", term=query, retmax=1)
                result = Entrez.read(handle)
                handle.close()
                time.sleep(RATE_DELAY)

                if not result["IdList"]:
                    print(f"    [AMR DB] No result for {gene_name}", file=sys.stderr)
                    continue

                uid = result["IdList"][0]
                fetch_handle = Entrez.efetch(db="nucleotide", id=uid,
                                             rettype="fasta", retmode="text")
                fasta_text = fetch_handle.read()
                fetch_handle.close()
                time.sleep(RATE_DELAY)

                # Annotate the FASTA header with gene and drug class
                lines = fasta_text.strip().split("\n")
                header = f">{gene_name} | {drug_class} | {lines[0][1:]}"
                sequence = "\n".join(lines[1:])
                out_f.write(f"{header}\n{sequence}\n\n")
                records_written += 1
                print(f"    [AMR DB] Fetched {gene_name}", file=sys.stderr)

            except Exception as e:
                print(f"    [AMR DB] Error fetching {gene_name}: {e}", file=sys.stderr)

    return records_written


def build_kmer_set(seq: str, k: int = KMER_SIZE) -> set:
    seq = seq.upper()
    return {seq[i:i+k] for i in range(len(seq) - k + 1) if "N" not in seq[i:i+k]}


def kmer_identity(query_kmers: set, ref_kmers: set) -> float:
    if not ref_kmers:
        return 0.0
    shared = len(query_kmers & ref_kmers)
    return shared / len(ref_kmers)


def load_amr_db(db_path: Path) -> list:
    """Return list of (gene_name, drug_class, kmer_set, gene_length)."""
    db = []
    for record in SeqIO.parse(db_path, "fasta"):
        parts = record.description.split("|")
        gene_name = parts[0].strip() if len(parts) > 0 else record.id
        drug_class = parts[1].strip() if len(parts) > 1 else "Unknown"
        seq = str(record.seq)
        db.append((gene_name, drug_class, build_kmer_set(seq), len(seq)))
    return db


def screen_genome(genome_files: list, sample_id: str, amr_db: list,
                  threshold: float) -> list:
    """Build k-mer set from all contigs in the genome and compare to AMR DB."""
    all_seq = ""
    for file_path in genome_files:
        for record in SeqIO.parse(file_path, "fasta"):
            all_seq += str(record.seq).upper()

    genome_kmers = build_kmer_set(all_seq)
    hits = []
    for gene_name, drug_class, ref_kmers, gene_len in amr_db:
        identity = kmer_identity(genome_kmers, ref_kmers)
        if identity >= threshold:
            hits.append({
                "gene": gene_name,
                "drug_class": drug_class,
                "identity": round(identity, 4),
                "gene_length": gene_len,
            })

    hits.sort(key=lambda x: x["identity"], reverse=True)
    return hits


def main():
    parser = argparse.ArgumentParser(description="Detect AMR genes in bacterial genomes")
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

        os.makedirs(".tmp", exist_ok=True)
        threshold = spec.get("identity_threshold", DEFAULT_IDENTITY)

        # Resolve AMR database
        if "amr_db" in spec:
            db_path = Path(spec["amr_db"])
            if not db_path.exists():
                raise FileNotFoundError(f"Custom AMR DB not found: {db_path}")
        else:
            db_path = Path(DEFAULT_DB_PATH)
            if not db_path.exists():
                print("  Building AMR reference database from NCBI (first run)...",
                      file=sys.stderr)
                count = fetch_amr_database(db_path)
                print(f"  AMR DB ready: {count} genes cached at {db_path}",
                      file=sys.stderr)

        amr_db = load_amr_db(db_path)
        if not amr_db:
            raise ValueError(f"AMR database is empty: {db_path}")

        print(f"  Loaded {len(amr_db)} AMR reference genes", file=sys.stderr)

        samples_results = []
        errors = []

        for query_str in spec.get("query_files", []):
            query_file = Path(query_str)
            if not query_file.exists():
                errors.append({"file": query_str, "error": "File not found"})
                continue
            try:
                sample_id = query_file.stem
                print(f"  Screening {sample_id} ...", file=sys.stderr)
                hits = screen_genome([query_file], sample_id, amr_db, threshold)
                samples_results.append({
                    "sample_id": sample_id,
                    "file": str(query_file),
                    "hits_found": len(hits),
                    "resistance_classes": list({h["drug_class"] for h in hits}),
                    "hits": hits,
                })
            except Exception as e:
                errors.append({"file": query_str, "error": str(e)})

        output_file = spec.get("output_file", ".tmp/amr_results.json")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(samples_results, f, indent=2)

        result = {
            "status": "ok",
            "amr_db_genes": len(amr_db),
            "identity_threshold": threshold,
            "samples": [
                {
                    "sample_id": s["sample_id"],
                    "hits_found": s["hits_found"],
                    "resistance_classes": s["resistance_classes"],
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
