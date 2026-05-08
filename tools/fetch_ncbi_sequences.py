"""
WAT tool: Download bacterial genome sequences from NCBI (GenBank / RefSeq / SRA).

Requires NCBI_EMAIL in .env. NCBI_API_KEY is optional but increases rate limit
from 3 to 10 requests/second.

Input JSON (--input or --input-file):
{
  "accessions": ["NC_000962.3", "NZ_CP012345.1"],   // Option A: known accessions
  "search_term": "Mycobacterium tuberculosis[Organism] complete genome[Title]",  // Option B
  "max_records": 10,        // used only with search_term (default 5)
  "output_dir": ".tmp/ncbi_sequences",   // optional
  "db": "nuccore"           // optional: nuccore (default) or nucleotide
}

Output JSON:
{
  "status": "ok",
  "downloaded": 3,
  "files": [
    {"accession": "NC_000962.3", "file": ".tmp/ncbi_sequences/NC_000962.3.fasta",
     "description": "Mycobacterium tuberculosis H37Rv ..."}
  ]
}
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from Bio import Entrez, SeqIO
from dotenv import load_dotenv

load_dotenv()

Entrez.email = os.getenv("NCBI_EMAIL", "")
api_key = os.getenv("NCBI_API_KEY", "")
if api_key:
    Entrez.api_key = api_key

RATE_LIMIT_DELAY = 0.11 if api_key else 0.34  # seconds between requests


def search_ncbi(term: str, db: str, max_records: int) -> list:
    handle = Entrez.esearch(db=db, term=term, retmax=max_records)
    record = Entrez.read(handle)
    handle.close()
    return record["IdList"]


def fetch_sequence(uid: str, db: str, output_dir: Path) -> dict:
    handle = Entrez.efetch(db=db, id=uid, rettype="fasta", retmode="text")
    text = handle.read()
    handle.close()
    time.sleep(RATE_LIMIT_DELAY)

    # Parse to get accession and description
    from io import StringIO
    records = list(SeqIO.parse(StringIO(text), "fasta"))
    if not records:
        raise ValueError(f"No sequences returned for ID {uid}")

    record = records[0]
    accession = record.id.split(".")[0]
    file_path = output_dir / f"{record.id}.fasta"

    with open(file_path, "w") as f:
        f.write(text)

    return {
        "accession": record.id,
        "file": str(file_path),
        "description": record.description,
        "length": len(record.seq),
    }


def main():
    parser = argparse.ArgumentParser(description="Download sequences from NCBI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="JSON string spec")
    group.add_argument("--input-file", help="Path to JSON spec file")
    parser.add_argument("--output-file", help="Optional path to write result JSON")
    args = parser.parse_args()

    try:
        if not Entrez.email:
            raise ValueError("NCBI_EMAIL is not set in .env — required for NCBI API calls")

        if args.input_file:
            with open(args.input_file) as f:
                spec = json.load(f)
        else:
            spec = json.loads(args.input)

        db = spec.get("db", "nuccore")
        output_dir = Path(spec.get("output_dir", ".tmp/ncbi_sequences"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Resolve accession IDs
        if "accessions" in spec:
            accessions = spec["accessions"]
            # Convert accessions to UIDs via esearch
            uid_list = []
            for acc in accessions:
                handle = Entrez.esearch(db=db, term=acc)
                record = Entrez.read(handle)
                handle.close()
                time.sleep(RATE_LIMIT_DELAY)
                uid_list.extend(record["IdList"])
        elif "search_term" in spec:
            max_records = spec.get("max_records", 5)
            uid_list = search_ncbi(spec["search_term"], db, max_records)
        else:
            raise ValueError("Provide either 'accessions' or 'search_term' in input")

        if not uid_list:
            raise ValueError("No sequences found matching the query")

        downloaded = []
        errors = []

        for uid in uid_list:
            try:
                info = fetch_sequence(uid, db, output_dir)
                downloaded.append(info)
                print(f"  Downloaded: {info['accession']} ({info['length']:,} bp)", file=sys.stderr)
            except Exception as e:
                errors.append({"uid": uid, "error": str(e)})

        result = {
            "status": "ok",
            "downloaded": len(downloaded),
            "files": downloaded,
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
