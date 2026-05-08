# Database-Backed Genomics Pipeline

## Objective
Extend the standard genomics pipeline so that every analysis run is persisted
to a local SQLite database. Results are queryable over time, enabling trend
analysis, multi-run comparisons, and downstream alerting and ML training.

## Prerequisites
- Complete Steps 1–6 of `genomics_pipeline.md` first (fetch → QC → SNP → AMR → phylo → report).
- SQLite — no installation required (Python stdlib).
- Database file lives at `.tmp/wat_genomics.db` (created by Step 7 below).

---

## Step 7 — Initialize the Database (first run only)
```bash
python tools/db_init.py --input '{"db_path": ".tmp/wat_genomics.db"}'
```
Re-running is safe — `CREATE TABLE IF NOT EXISTS` protects all tables.
Check `schema_version: 1` in the output to confirm success.

---

## Step 8 — Store the Run Results
Create a JSON spec file (e.g., `.tmp/run_spec.json`):
```json
{
  "db_path": ".tmp/wat_genomics.db",
  "run_metadata": {
    "researcher": "Dr. Meena Niazi",
    "study_name": "One-Health AMR Survey 2026",
    "pathogen": "Klebsiella pneumoniae",
    "source_type": "human",
    "country": "Pakistan",
    "region": "Punjab",
    "facility": "Lahore General Hospital"
  },
  "qc_file":    ".tmp/qc_report.json",
  "snp_file":   ".tmp/snp_results.json",
  "amr_file":   ".tmp/amr_results.json",
  "phylo_file": ".tmp/phylo/results.json"
}
```
Then run:
```bash
python tools/db_store_run.py --input-file .tmp/run_spec.json
```
Capture the `run_id` UUID from the output — you will need it for alerting and ML.
Missing result files are silently skipped (partial runs are valid).

---

## Step 9 — Query Historical Data (optional)
```bash
# List all stored runs
python tools/db_query.py --input '{"query_type": "runs_list"}'

# AMR gene frequency trend for a specific gene + region over 365 days
python tools/db_query.py --input '{
  "query_type": "amr_trend",
  "filters": {"gene": "blaNDM-1", "region": "Punjab", "days_back": 365}
}'

# Outbreak check: same gene in 3+ samples within 90 days
python tools/db_query.py --input '{
  "query_type": "outbreak_check",
  "filters": {"gene": "blaNDM-1", "region": "Punjab",
               "outbreak_window_days": 90, "outbreak_sample_threshold": 3}
}'

# Full summary for one run
python tools/db_query.py --input '{
  "query_type": "run_summary",
  "filters": {"run_id": "your-run-uuid-here"}
}'
```

---

## Source Metadata — `source_type` Field
The `source_type` field supports One-Health tracking across the human-animal-environment interface:

| Value | Use case |
|-------|----------|
| `human` | Clinical isolates from patients |
| `animal` | Livestock, companion animals, wildlife |
| `environment` | Soil, water, food, hospital surfaces |
| `unknown` | Source not recorded (default) |

---

## Database Maintenance

**Backup:** Copy `.tmp/wat_genomics.db` to a safe location regularly.
```bash
copy .tmp\wat_genomics.db backups\wat_genomics_%date%.db
```

**Browse with UI:** Open `.tmp/wat_genomics.db` in
[DB Browser for SQLite](https://sqlitebrowser.org/) (free, cross-platform).

**Upgrade to PostgreSQL:** The schema DDL in `tools/db_init.py` (`SCHEMA_SQL`)
is PostgreSQL-compatible. Replace `INTEGER PRIMARY KEY AUTOINCREMENT` with
`SERIAL PRIMARY KEY`, and connect via `psycopg2` instead of `sqlite3` in
each tool. All SQL queries use standard SQL with no SQLite-specific syntax.

**Reset database:** Delete `.tmp/wat_genomics.db` and re-run Step 7.
Warning: all stored run data will be lost.

---

## Known Issues
- **Duplicate runs:** Calling `db_store_run.py` twice with the same `run_id` will
  overwrite the run header but may insert duplicate sample/AMR rows. Always use a
  fresh `run_id` (auto-generated UUID) for each new pipeline run.
- **Very large SNP sets (> 10,000 variants):** Only the first 10,000 SNP variants
  per sample are stored in the DB (to prevent bloat). The full list remains in
  `.tmp/snp_results.json`.
