# One-Health AMR Surveillance — End-to-End Workflow

## Objective
Integrate genomic and phenotypic AMR data from human, animal, and environmental
sources into a single longitudinal surveillance system. Detect resistance hotspots,
forecast emerging threats, and generate actionable intelligence for One-Health
policy makers, epidemiologists, and clinical teams.

## One-Health Framing
Antimicrobial resistance does not respect species boundaries. The same resistance
genes (e.g., blaNDM-1, mcr-1) appear in human pathogens, livestock, companion
animals, river water, and hospital sewage. This pipeline uses `source_type` to
tag every sample's origin:

| `source_type` | Examples |
|---------------|---------|
| `human` | Clinical isolates from patients (blood, urine, sputum, wound) |
| `animal` | Livestock (poultry, cattle, swine), companion animals, wildlife |
| `environment` | River water, irrigation canals, hospital drains, soil, food |

---

## Full Pipeline Run — One-Health Protocol

### Phase 1: Initialize (first time only)
```bash
python tools/db_init.py --input '{"db_path": ".tmp/wat_genomics.db"}'
```

---

### Phase 2A: Genomic Pathway
For each batch of WGS assemblies (human, animal, or environment):

```bash
# 2A.1 Catalog local files
python tools/fetch_local_sequences.py --input '{"directory": "/path/to/fastas"}'

# 2A.2 QC
python tools/qc_sequences.py --input '{
  "files": ["/path/sample1.fasta", ...],
  "output_file": ".tmp/qc_report.json"
}'

# 2A.3 SNP detection (requires reference genome)
python tools/snp_detection.py --input '{
  "reference_file": "/path/reference.fasta",
  "query_files": ["/path/sample1.fasta", ...],
  "output_file": ".tmp/snp_results.json"
}'

# 2A.4 AMR detection
python tools/amr_detection.py --input '{
  "query_files": ["/path/sample1.fasta", ...],
  "output_file": ".tmp/amr_results.json"
}'

# 2A.5 Phylogenetics (≥3 genomes)
python tools/phylogenetics.py --input '{
  "files": ["/path/sample1.fasta", ...],
  "output_dir": ".tmp/phylo"
}'

# 2A.6 Store in database — SET source_type appropriately
python tools/db_store_run.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "run_metadata": {
    "researcher": "Dr. Niazi",
    "study_name": "One-Health Punjab Survey 2026",
    "pathogen": "Klebsiella pneumoniae",
    "source_type": "animal",
    "country": "Pakistan",
    "region": "Punjab"
  },
  "qc_file":    ".tmp/qc_report.json",
  "snp_file":   ".tmp/snp_results.json",
  "amr_file":   ".tmp/amr_results.json",
  "phylo_file": ".tmp/phylo/results.json"
}'
```
Repeat for each batch, changing `source_type` per cohort.

---

### Phase 2B: Phenotypic Pathway
For AST data from any source:
```bash
python tools/phenotypic_analysis.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "ast_file": "/path/to/ast_data.csv",
  "run_metadata": {
    "pathogen": "Klebsiella pneumoniae",
    "source_type": "human",
    "country": "Pakistan",
    "region": "Punjab"
  },
  "output_file": ".tmp/phenotypic_results.json"
}'
```

Genotype–phenotype concordance (when same sample IDs in both genomic + phenotypic):
```bash
python tools/genotype_phenotype.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "uuid-of-genomic-run"
}'
```

---

### Phase 3: Public Health Alert
```bash
# Score the alert
python tools/alert_score.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "uuid-here",
  "outbreak_window_days": 90,
  "outbreak_sample_threshold": 3,
  "output_file": ".tmp/alert_result.json"
}'

# Generate Word brief
python tools/alert_report.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "run_id": "uuid-here",
  "output_path": ".tmp/alert_report.docx"
}'

# Push to Google Sheets dashboard
python tools/sheets_dashboard.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "spreadsheet_id": "YOUR_SHEET_ID",
  "sheet_name": "AMR_Alerts"
}'
```

---

### Phase 4: ML Predictions (after ≥20 samples accumulated)
```bash
# Train model
python tools/ml_train.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_type": "random_forest",
  "target_variable": "amr_phenotype_meropenem",
  "feature_set": "genomic",
  "filters": {"min_samples": 20},
  "output_dir": ".tmp/models"
}'

# Predict on new run
python tools/ml_predict.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "run_id": "uuid-of-new-run"
}'

# Back up model to Google Drive
python tools/drive_backup.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "folder_name": "WAT_ML_Models"
}'
```

---

### Phase 5: Forecasting (after ≥6 monthly time points)
```bash
# Forecast carbapenem resistance rate 6 months ahead
python tools/forecast_trends.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "forecast_type": "resistance_rate",
  "filters": {
    "antibiotic": "Meropenem",
    "region": "Punjab",
    "days_back": 730
  },
  "forecast_horizon_months": 6,
  "output_file": ".tmp/forecast_result.json"
}'

# Forecast MDR rate
python tools/forecast_trends.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "forecast_type": "mdr_rate",
  "filters": {"region": "Punjab"},
  "forecast_horizon_months": 6
}'

# Forecast gene spread
python tools/forecast_trends.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "forecast_type": "gene_frequency",
  "filters": {"gene": "blaNDM-1", "region": "Punjab"},
  "forecast_horizon_months": 6
}'
```

---

## Cross-Source AMR Comparison

To compare resistance gene presence across human, animal, and environmental sources
(One-Health analysis):
```bash
python tools/db_query.py --input '{
  "query_type": "amr_trend",
  "filters": {
    "gene": "blaNDM-1",
    "region": "Punjab",
    "days_back": 365
  }
}'
```

The `source_type` field is returned in results; filter or pivot in pandas/Excel
to compare across human/animal/environment.

---

## Reporting Schedule (Recommended)

| Frequency | Action |
|-----------|--------|
| Per batch | Run Phases 2A/2B → Phase 3 alert |
| Weekly | Check Google Sheets dashboard for new RED/ORANGE alerts |
| Monthly | Run `resistance_rate` query; update trend charts |
| Quarterly | Run forecasting (`forecast_trends.py`) for all key antibiotics |
| Bi-annually | Retrain ML models with accumulated data |
| Annually | Full One-Health report using `generate_genomics_report.py` + phenotypic results |

---

## Key Policy Outputs

| Tool Output | Policy Relevance |
|-------------|-----------------|
| Alert level RED | Activate national AMR emergency response plan |
| Outbreak signal | Initiate epidemiological investigation; notify WHO IHR |
| Rising resistance trend (forecast) | Revise empirical treatment guidelines |
| Concordance < 80% | Review diagnostic laboratory protocols |
| Animal/environment sources sharing same gene as human cases | Zoonotic transmission investigation; restrict antibiotic use in animal husbandry |
| MDR rate > 50% | Recommend reserve antibiotic access programs |

---

## Known Limitations
- This pipeline analyzes pre-assembled genomes. Raw FASTQ reads must be assembled
  first (e.g., with SPAdes or Shovill) before entering the genomic pathway.
- SNP detection is most accurate for samples within the same species (>70% ANI).
  Cross-species comparisons should use phylogenetics (k-mer Jaccard distance) instead.
- The forecast requires ≥6 monthly data points. New surveillance programs will not
  produce meaningful forecasts until approximately 6 months of data have been collected.
- ML model accuracy is limited by the size and diversity of the training set.
  Predictions from models trained on < 50 samples should be treated as indicative, not definitive.
