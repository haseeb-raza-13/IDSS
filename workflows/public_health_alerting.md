# Public Health Alerting Workflow

## Objective
After each genomic analysis run is stored in the database, automatically score
the run for AMR threat level, generate a Word alert brief, and push the alert
to a shared Google Sheets dashboard where public health professionals and
epidemiologists can monitor resistance trends in real time.

## Prerequisites
- Database initialized and run stored: `db_init.py` + `db_store_run.py` (Phase 1)
- Google Sheets API enabled (credentials.json at project root)
- A Google Sheets spreadsheet pre-created (copy the spreadsheet ID from the URL)

---

## Alert Scoring Logic

| Signal | Score Added |
|--------|-------------|
| MDR pattern (≥3 drug classes resistant) | +20 |
| XDR pattern | +40 |
| PDR pattern | +40 |
| High-severity gene detected per gene | +25 (max +50) |
| Outbreak signal (≥3 samples, same gene, same region, ≤90 days) | +30 |
| New resistance (first DB detection in this region) | +15 |

**High-severity genes:** blaNDM-1, blaNDM-5, blaKPC-2, blaKPC-3, blaOXA-48,
blaOXA-232, mcr-1, mcr-2, vanA, blaVIM-1, blaVIM-2, blaIMP-1

**Alert levels:**

| Score | Level | Meaning |
|-------|-------|---------|
| 70–100 | RED | Critical — escalate to national health authority immediately |
| 45–69 | ORANGE | High — notify regional public health unit within 24 hours |
| 20–44 | YELLOW | Moderate — enhanced monitoring and IPC review |
| 0–19 | GREEN | Low — routine surveillance, no immediate action |

---

## Step 1 — Score the Alert
```bash
python tools/alert_score.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "run_id": "your-run-uuid-here",
  "outbreak_window_days": 90,
  "outbreak_sample_threshold": 3,
  "output_file": ".tmp/alert_result.json"
}'
```
The alert record is written to `alert_records` table automatically.

---

## Step 2 — Generate Alert Report (Word Document)
```bash
python tools/alert_report.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "run_id": "your-run-uuid-here",
  "output_path": ".tmp/alert_report.docx"
}'
```
The report contains 7 sections targeting public health officials:
1. Alert header (level + score + date + region)
2. Executive summary (plain language)
3. Trigger summary (bullet list)
4. AMR findings table (genes, drug classes, sample count)
5. Outbreak context table (if outbreak signal triggered)
6. Recommended actions (tiered protocol per level)
7. Technical details (run ID, pipeline version)

---

## Step 3 — Push to Google Sheets Dashboard

### One-time setup:
1. Create a new Google Sheet at sheets.google.com
2. Copy the spreadsheet ID from the URL: `https://docs.google.com/spreadsheets/d/**ID_HERE**/edit`
3. Download OAuth 2.0 credentials from Google Cloud Console → place as `credentials.json` at project root
4. First run will open a browser for authentication; token is cached in `token.json`

```bash
python tools/sheets_dashboard.py --input '{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "spreadsheet_id": "YOUR_SPREADSHEET_ID_HERE",
  "sheet_name": "AMR_Alerts"
}'
```
First run writes the header row and applies color coding (RED rows in red, etc.).
Subsequent runs append one row per pipeline run.

**Share the spreadsheet** with public health colleagues:
In Google Sheets → Share → Anyone with link can view.
The `spreadsheet_url` is returned in the tool output.

---

## Recommended Action Protocols

### RED — Immediate
- Notify NIH / national public health authority
- Activate enhanced IPC protocols in affected facilities
- Initiate contact tracing and patient screening
- Implement cohort isolation; restrict inter-ward patient movement
- Convene emergency multi-disciplinary team (ID, IPC, microbiology)
- Report to WHO IHR focal point if international concern criteria are met
- Increase sampling frequency; send isolates to reference laboratory for WGS
- Review empirical antibiotic prescribing for the affected pathogen

### ORANGE — Urgent (within 24–48 hrs)
- Notify regional/provincial public health unit
- Double surveillance sampling frequency
- Enhanced hand hygiene and contact precautions in affected wards
- Review antibiotic stewardship guidelines for detected resistance class
- Convene IPC team review within 72 hours

### YELLOW — Monitor
- Flag for secondary reference laboratory confirmation
- Increase monitoring of patients harboring the organism
- Notify ward infection control nurse
- Review prescribing patterns for affected antibiotic classes
- Document in institutional AMR surveillance log

### GREEN — Routine
- Continue standard AMR surveillance
- Maintain baseline IPC measures
- Review at next scheduled AMR committee meeting

---

## Google Sheets Dashboard Design

The `AMR_Alerts` sheet is an append-only log used as the data source.
Public health teams can build a summary view using Google Sheets QUERY formulas:

```
=QUERY(AMR_Alerts!A:Q, "SELECT C, COUNT(A) WHERE C='RED' GROUP BY C LABEL COUNT(A) 'RED Alerts'")
```

Recommended additional sheets (created manually by the epidemiologist):
- **Regional Map**: COUNTIF-based table of alerts per region per quarter
- **Gene Tracker**: Frequency of each high-severity gene over time
- **Trend Chart**: Line chart from resistance_rate data (from forecast output)

---

## Known Issues
- **Google OAuth first run**: Requires browser access. On headless servers, use
  service account credentials instead of OAuth (modify `get_credentials()` in
  `sheets_dashboard.py` to use `service_account.Credentials`).
- **Outbreak lookback precision**: The 90-day window uses `created_at` timestamp
  in the DB (time of analysis), not the biological `collection_date`. If samples
  are batch-submitted weeks after collection, the window may undercount clusters.
  Use `collection_date` from `phenotypic_samples` for more accurate epidemiological
  analysis via `db_query.py`.
- **Score inflation**: If the same high-severity gene appears in many historical
  runs for the same region, the "new resistance" bonus will not trigger (correctly).
  Routinely purge test runs from the DB to avoid skewing the baseline.
