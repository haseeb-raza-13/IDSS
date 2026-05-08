# Genomics Analysis Pipeline

## Objective
Analyze bacterial whole-genome sequencing (WGS) data to detect SNPs, identify
antimicrobial resistance (AMR) genes, build phylogenetic trees, and generate a
comprehensive Word document report. Supports both local FASTA/FASTQ files and
NCBI-downloaded genomes.

## Required Inputs
- Bacterial genome assemblies as FASTA files **or** NCBI accession numbers
- A reference genome FASTA for SNP detection (same species, ideally a named reference strain)
- NCBI_EMAIL set in `.env` (required for NCBI download and AMR DB construction)

## Environment Variables (`.env`)
```
NCBI_EMAIL=your@email.com        # Required — NCBI blocks anonymous Entrez calls
NCBI_API_KEY=your_key_here       # Optional but recommended: raises rate limit 3→10 req/s
```

---

## Pipeline Steps

### Step 1 — Acquire Sequence Data

**Option A — Local FASTA/FASTQ files:**
```
python tools/fetch_local_sequences.py --input '{"directory": "/path/to/sequences"}'
```
Returns a sample catalog and saves `.tmp/sequences_index.json`.

**Option B — Download from NCBI:**
```
python tools/fetch_ncbi_sequences.py --input '{
  "accessions": ["NC_000962.3", "NZ_CP012345.1"],
  "output_dir": ".tmp/ncbi_sequences"
}'
```
Or use a search term instead of accessions:
```
python tools/fetch_ncbi_sequences.py --input '{
  "search_term": "Klebsiella pneumoniae[Organism] complete genome[Title]",
  "max_records": 10,
  "output_dir": ".tmp/ncbi_sequences"
}'
```

Collect the `"file"` paths from the output for the next steps.

---

### Step 2 — Quality Control
```
python tools/qc_sequences.py --input '{
  "files": ["/path/genome1.fasta", "/path/genome2.fasta"],
  "output_file": ".tmp/qc_report.json"
}'
```
**Review flags before proceeding:**
- GC content outside 30–80% → unusual taxon or contamination
- N content > 5% → poor assembly; exclude from SNP/phylo analysis
- Total length < 500 kb → likely incomplete; exclude
- Total length > 15 Mb → likely contaminated; exclude

---

### Step 3 — SNP Detection
```
python tools/snp_detection.py --input '{
  "reference_file": "/path/reference.fasta",
  "query_files": ["/path/genome1.fasta", "/path/genome2.fasta"],
  "output_file": ".tmp/snp_results.json"
}'
```
**Notes:**
- Use the same reference for all samples to ensure comparable SNP coordinates.
- For a canonical reference, download the type strain from NCBI (e.g., H37Rv for M. tuberculosis,
  ATCC 13883 for K. pneumoniae).
- Runtime: ~2–10 min per genome pair depending on genome size and SNP density.
- Full SNP list per sample saved to `output_file`; summary returned to stdout.

---

### Step 4 — AMR Detection
```
python tools/amr_detection.py --input '{
  "query_files": ["/path/genome1.fasta", "/path/genome2.fasta"],
  "output_file": ".tmp/amr_results.json",
  "identity_threshold": 0.80
}'
```
**First-run behavior:** Fetches 22 curated AMR gene sequences from NCBI and caches them
at `.tmp/amr_db.fasta`. Subsequent runs skip the download and use the cache.

**Custom database:** Supply `"amr_db": "/path/custom.fasta"` to use your own gene
sequences (e.g., from CARD or ResFinder) instead of the auto-built one.

**Threshold guidance:**
- 0.90+ → highly confident hit (very close match)
- 0.80–0.89 → likely hit, may be a variant or truncated gene
- Below 0.80 → too low; likely background k-mer overlap

---

### Step 5 — Phylogenetics
```
python tools/phylogenetics.py --input '{
  "files": ["/path/genome1.fasta", "/path/genome2.fasta", "/path/genome3.fasta"],
  "output_dir": ".tmp/phylo",
  "tree_method": "nj",
  "kmer_size": 21
}'
```
**Minimum 3 genomes required.**

Outputs:
- `.tmp/phylo/tree.nwk` — Newick format tree (import into iTOL, FigTree, etc.)
- `.tmp/phylo/tree_ascii.txt` — ASCII visualization for quick inspection
- `.tmp/phylo/results.json` — distance matrix + metadata

**k-mer size guidance:**
- k=21 (default): good for species-level discrimination
- k=31: higher specificity, better for closely related strains
- k=15: use only if genomes are very divergent

---

### Step 6 — Generate Report
```
python tools/generate_genomics_report.py --input '{
  "study_name": "My Bacterial WGS Study",
  "output_path": ".tmp/genomics_report.docx",
  "qc_file":    ".tmp/qc_report.json",
  "snp_file":   ".tmp/snp_results.json",
  "amr_file":   ".tmp/amr_results.json",
  "phylo_file": ".tmp/phylo/results.json"
}'
```
Generates a Word document with all tables, metrics, and the ASCII phylogenetic tree.
Any missing result files are silently skipped (partial reports are valid).

---

## Expected Outputs

| File | Contents |
|------|----------|
| `.tmp/sequences_index.json` | Sample catalog from local scan |
| `.tmp/ncbi_sequences/*.fasta` | Downloaded genome FASTA files |
| `.tmp/qc_report.json` | QC metrics per sample |
| `.tmp/snp_results.json` | SNP/indel calls per sample vs reference |
| `.tmp/amr_db.fasta` | Cached AMR reference gene sequences |
| `.tmp/amr_results.json` | AMR gene hits per sample |
| `.tmp/phylo/tree.nwk` | Newick phylogenetic tree |
| `.tmp/phylo/tree_ascii.txt` | ASCII tree visualization |
| `.tmp/phylo/results.json` | Distance matrix + phylo metadata |
| `.tmp/genomics_report.docx` | Full compiled analysis report |

---

## Edge Cases & Known Issues

**Large genomes (> 6 Mb):**
SNP detection uses 50 kb chunks; runtime scales linearly with genome size. A 6 Mb
genome takes ~10–15 min per sample pair. No action needed; just allow more time.

**Closely related strains (< 100 SNPs):**
k-mer distance matrix may show near-zero distances; the NJ tree topology is still
valid but branch lengths will be very short. Inspect the SNP matrix directly.

**Distantly related species (< 70% ANI):**
k-mer Jaccard distance becomes unreliable below ~70% ANI. Do not compare genomes
from different genera in the same phylogenetic analysis.

**NCBI rate limits:**
Without API key: 3 requests/second. With NCBI_API_KEY: 10 requests/second.
The tools already respect these limits. If you hit 429 errors, add NCBI_API_KEY.

**AMR database staleness:**
Delete `.tmp/amr_db.fasta` to force a fresh download with the latest NCBI sequences.

**Plasmid-borne vs chromosomal AMR:**
The k-mer approach detects resistance genes regardless of genomic location. To
determine chromosomal vs plasmid location, a separate plasmid classification tool
(e.g., PlasmidFinder) would be needed.

**FASTQ files in SNP/AMR/phylo steps:**
These tools only accept assembled FASTA files. If starting from raw reads, you must
first assemble them (e.g., with SPAdes or Shovill) before running this pipeline.

---

## Quick Reference: Full Pipeline Run

```bash
# 1. Download genomes
python tools/fetch_ncbi_sequences.py --input '{"accessions":["NC_000962.3"],"output_dir":".tmp/ncbi"}'

# 2. QC
python tools/qc_sequences.py --input '{"files":[".tmp/ncbi/NC_000962.3.fasta"],"output_file":".tmp/qc_report.json"}'

# 3. SNPs (requires a reference)
python tools/snp_detection.py --input '{"reference_file":"ref.fasta","query_files":[".tmp/ncbi/NC_000962.3.fasta"],"output_file":".tmp/snp_results.json"}'

# 4. AMR
python tools/amr_detection.py --input '{"query_files":[".tmp/ncbi/NC_000962.3.fasta"],"output_file":".tmp/amr_results.json"}'

# 5. Phylogenetics (need 3+ genomes)
python tools/phylogenetics.py --input '{"files":["g1.fasta","g2.fasta","g3.fasta"],"output_dir":".tmp/phylo"}'

# 6. Report
python tools/generate_genomics_report.py --input '{"study_name":"My Study","output_path":".tmp/report.docx","qc_file":".tmp/qc_report.json","snp_file":".tmp/snp_results.json","amr_file":".tmp/amr_results.json","phylo_file":".tmp/phylo/results.json"}'
```
