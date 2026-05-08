# Phenotypic Analysis Pathway (AST Data)

## Objective
Ingest laboratory antimicrobial susceptibility testing (AST) data — from disk
diffusion, E-test (Epsilometer), or broth microdilution — and compute resistance
rates, MDR/XDR/PDR classifications, and temporal trend analysis. Results are stored
in the database and can be linked to genomic AMR data via concordance analysis.

## Prerequisites
- Database initialized: `python tools/db_init.py`
- AST data in CSV or Excel format (column spec below)
- `pandas` and `openpyxl` installed (already in `requirements.txt`)

---

## Required AST File Format

**Required columns (case-insensitive, spaces auto-normalized):**

| Column | Description | Example values |
|--------|-------------|----------------|
| `sample_id` | Unique isolate identifier | `KP_001`, `ISO_2024_045` |
| `pathogen_name` | Bacterial species name | `Klebsiella pneumoniae` |
| `date` | Collection date | `2026-01-15` or `2026-01` |
| `location` | General location string | `Ward 3, PIMS` |
| `antibiotic` | Antibiotic name (matches DRUG_CLASS_MAP) | `Meropenem`, `Ciprofloxacin` |
| `interpretation` | AST result | `S`, `I`, or `R` |

**Optional columns:**

| Column | Description |
|--------|-------------|
| `mic_value` | MIC in mg/L (e.g., `0.5`, `>256`) |
| `zone_diameter` | Disk zone in mm |
| `test_method` | `disk_diffusion`, `etest`, `broth_microdilution`, `other` |
| `source_type` | `human`, `animal`, `environment`, `unknown` |
| `facility` | Hospital/lab name |
| `country` | Country name |
| `region` | Region/province/state |
| `breakpoint_standard` | `EUCAST_2024`, `CLSI_2024`, etc. |

**Supported antibiotics** (partial list — full map in `tools/phenotypic_analysis.py`):
Ampicillin, Amoxicillin-Clavulanate, Piperacillin-Tazobactam, Ceftriaxone,
Ceftazidime, Cefepime, Meropenem, Imipenem, Ertapenem, Ciprofloxacin, Levofloxacin,
Gentamicin, Amikacin, Tobramycin, Tetracycline, Tigecycline, Vancomycin, Linezolid,
Trimethoprim-Sulfamethoxazole, Colistin, Chloramphenicol, Erythromycin.

---

## Step 1 — Ingest and Analyze AST Data
```bash
python tools/phenotypic_analysis.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "ast_file": "/path/to/ast_data.csv",
  "run_metadata": {
    "researcher": "Dr. Ahmed",
    "study_name": "ESKAPE Surveillance 2026",
    "pathogen": "Klebsiella pneumoniae",
    "country": "Pakistan",
    "region": "Punjab",
    "source_type": "human"
  },
  "output_file": ".tmp/phenotypic_results.json"
}'
```

**Outputs:**
- `mdr_summary` — count of Susceptible / MDR / XDR / PDR isolates
- `resistance_rates` — rate per antibiotic, region, quarterly period
- `trend_analysis` — slope (% per month), direction (rising/falling/stable)

**MDR Classification Thresholds:**
- **MDR**: Resistant to ≥ 3 drug classes
- **XDR**: Resistant to all but ≤ 2 drug classes
- **PDR**: Resistant to all tested drug classes

---

## Step 2 — Genotype–Phenotype Concordance (if genomic data available)
Run this only if the same sample IDs appear in both genomic AMR results and
the AST file.
```bash
python tools/genotype_phenotype.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "uuid-of-the-genomic-run",
  "output_file": ".tmp/geno_pheno_concordance.json"
}'
```

**Interpreting output:**
- `concordance_rate_percent` > 85% = good genotypic AMR prediction
- `False_Negative_Genomic` cases: gene not detected but phenotypically resistant
  → consider expanding AMR gene database or checking plasmid-borne genes
- `False_Positive_Genomic` cases: gene detected but phenotypically susceptible
  → gene may be non-functional, silenced, or identity threshold too low

---

## Step 3 — Query Resistance Rates
```bash
python tools/db_query.py --input '{
  "query_type": "resistance_rate",
  "filters": {
    "antibiotic": "Meropenem",
    "region": "Punjab",
    "days_back": 365
  }
}'
```

---

## Trend Analysis Guidance

| Slope (% / month) | Interpretation |
|---|---|
| > 0.5 | Rising — flag for enhanced surveillance |
| −0.5 to 0.5 | Stable — continue routine monitoring |
| < −0.5 | Falling — intervention may be working; continue |

Trends with < 6 monthly data points should not be over-interpreted.

---

## Common LIMS Export Formats
Most laboratory information management systems (LIMS) export data in formats
that need column renaming before use:

**VITEK 2 exports:** Rename `Organism` → `pathogen_name`, `Drug` → `antibiotic`,
`S/I/R` → `interpretation`, `MIC` → `mic_value`.

**WHONET exports:** Already use standard column names. Set `interpretation`
from the `SIR` column.

**Manual lab registers:** Use the Excel template column spec above. Save as CSV
(UTF-8, comma-separated).

---

## Known Issues
- **Antibiotic name mismatches:** The tool uses exact string matching against
  `DRUG_CLASS_MAP`. If an antibiotic is not in the map, its drug class defaults
  to "Other" and it will not contribute to MDR classification. Add custom entries
  to the `DRUG_CLASS_MAP` dict in `tools/phenotypic_analysis.py`.
- **MIC string values** (e.g., `">256"`) are ignored (stored as `None`). Pre-process
  these to numeric values before running the tool if MIC-based ML features are needed.
- **XDR classification** depends on knowing the full set of relevant drug classes
  per pathogen. The current implementation uses the global `ALL_DRUG_CLASSES` list
  (all classes in the map). For organism-specific XDR criteria (per ECDC/CDC
  definitions), extend `classify_mdr()` with organism-specific class lists.
