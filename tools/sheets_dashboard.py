"""
WAT tool: Push a public health alert to a Google Sheets dashboard.

Appends one row per run to an append-only alert log sheet. On first write,
creates the header row and applies conditional formatting (RED rows highlighted).
Returns the shareable URL for the spreadsheet.

Requires Google OAuth credentials. On first run, opens a browser for
authentication. Stores token at token.json in the project root.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "alert_file": ".tmp/alert_result.json",
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "sheet_name": "AMR_Alerts",               // optional, default shown
  "create_if_missing": true                  // optional, default true
}

Output JSON:
{
  "status": "ok",
  "spreadsheet_id": "...",
  "sheet_name": "AMR_Alerts",
  "row_written": 47,
  "spreadsheet_url": "https://docs.google.com/spreadsheets/d/..."
}

Dashboard columns (A–Q):
  A: Timestamp    B: Run ID       C: Alert Level  D: Alert Score
  E: Pathogen     F: Region       G: Country      H: Researcher
  I: Study Name   J: MDR          K: XDR          L: Outbreak Signal
  M: New Resist.  N: High-Sev Genes  O: Triggers  P: Report Path
  Q: Samples
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

DEFAULT_DB = ".tmp/wat_genomics.db"
DEFAULT_SHEET = "AMR_Alerts"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADERS = [
    "Timestamp", "Run ID", "Alert Level", "Alert Score",
    "Pathogen", "Region", "Country", "Researcher",
    "Study Name", "MDR Detected", "XDR Detected", "Outbreak Signal",
    "New Resistance", "High-Severity Genes", "Triggers",
    "Report Path", "Samples Analyzed",
]

# Row background color by alert level
LEVEL_COLORS = {
    "RED":    {"red": 0.96, "green": 0.80, "blue": 0.80},
    "ORANGE": {"red": 1.0,  "green": 0.90, "blue": 0.75},
    "YELLOW": {"red": 1.0,  "green": 0.97, "blue": 0.75},
    "GREEN":  {"red": 0.85, "green": 0.96, "blue": 0.85},
}


def get_credentials():
    token_path = Path("token.json")
    creds_path = Path("credentials.json")
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    "credentials.json not found. Download OAuth 2.0 credentials from "
                    "Google Cloud Console and place at project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def get_or_create_sheet(sheets_svc, spreadsheet_id: str, sheet_name: str,
                         create_if_missing: bool) -> int:
    """Return the sheet ID (gid). Creates the sheet if absent and allowed."""
    meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]

    if not create_if_missing:
        raise ValueError(f"Sheet '{sheet_name}' not found and create_if_missing is false")

    resp = sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def ensure_header(sheets_svc, spreadsheet_id: str, sheet_name: str) -> bool:
    """Write header row if A1 is empty. Returns True if headers were written."""
    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1:A1",
    ).execute()
    existing = result.get("values", [])
    if existing and existing[0]:
        return False  # header already present

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()
    return True


def append_row(sheets_svc, spreadsheet_id: str, sheet_name: str,
               row: list) -> int:
    result = sheets_svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    updated_range = result.get("updates", {}).get("updatedRange", "")
    try:
        row_num = int(updated_range.split("!")[1].split(":")[0][1:])
    except Exception:
        row_num = -1
    return row_num


def apply_row_color(sheets_svc, spreadsheet_id: str, sheet_id: int,
                    row_index: int, level: str) -> None:
    color = LEVEL_COLORS.get(level, LEVEL_COLORS["GREEN"])
    col_count = len(HEADERS)
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index - 1,
                        "endRowIndex": row_index,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                            "textFormat": {
                                "bold": level in ("RED", "ORANGE"),
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]
        },
    ).execute()


def load_run_info(db_path: str, run_id: str) -> dict:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    sample_count = conn.execute(
        "SELECT COUNT(*) FROM samples WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    conn.close()
    info = dict(row) if row else {}
    info["sample_count"] = sample_count
    return info


def build_row(alert: dict, run_info: dict) -> list:
    return [
        alert.get("run_id", "")[:10] + "T" + alert.get("run_id", "")[11:] if False else
        run_info.get("timestamp", ""),
        alert.get("run_id", ""),
        alert.get("alert_level", ""),
        str(alert.get("alert_score", 0)),
        alert.get("pathogen", ""),
        alert.get("region", ""),
        run_info.get("country", ""),
        run_info.get("researcher", ""),
        run_info.get("study_name", ""),
        "YES" if alert.get("mdr_detected") else "NO",
        "YES" if alert.get("xdr_detected") else "NO",
        "YES" if alert.get("outbreak_signal") else "NO",
        "YES" if alert.get("new_resistance") else "NO",
        ", ".join(alert.get("high_severity_genes", []) or []),
        " | ".join(alert.get("triggers", []) or [])[:500],
        alert.get("report_path", ""),
        str(alert.get("samples_in_run", run_info.get("sample_count", ""))),
    ]


def update_sheets_row_in_db(db_path: str, run_id: str, row_num: int) -> None:
    if not Path(db_path).exists():
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE alert_records SET sheets_row=? WHERE run_id=?", (row_num, run_id)
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Push alert to Google Sheets dashboard")
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

        alert_file = spec.get("alert_file")
        if not alert_file or not Path(alert_file).exists():
            raise FileNotFoundError(f"alert_file not found: {alert_file}")

        with open(alert_file) as f:
            alert = json.load(f)

        spreadsheet_id = spec.get("spreadsheet_id")
        if not spreadsheet_id:
            raise ValueError("'spreadsheet_id' is required")

        sheet_name = spec.get("sheet_name", DEFAULT_SHEET)
        create_if_missing = spec.get("create_if_missing", True)
        db_path = spec.get("db_path", DEFAULT_DB)

        run_id = alert.get("run_id", "")
        run_info = load_run_info(db_path, run_id)

        creds = get_credentials()
        sheets_svc = build("sheets", "v4", credentials=creds)

        sheet_id = get_or_create_sheet(
            sheets_svc, spreadsheet_id, sheet_name, create_if_missing
        )
        ensure_header(sheets_svc, spreadsheet_id, sheet_name)

        row_data = build_row(alert, run_info)
        row_num = append_row(sheets_svc, spreadsheet_id, sheet_name, row_data)

        if row_num > 0:
            apply_row_color(
                sheets_svc, spreadsheet_id, sheet_id, row_num,
                alert.get("alert_level", "GREEN")
            )
            update_sheets_row_in_db(db_path, run_id, row_num)

        spreadsheet_url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        )

        result = {
            "status": "ok",
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "row_written": row_num,
            "spreadsheet_url": spreadsheet_url,
        }

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
