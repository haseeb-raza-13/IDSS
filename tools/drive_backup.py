"""
WAT tool: Upload a trained ML model to Google Drive and update the database.

Uploads the .joblib model file to a Google Drive folder, shares it with
"anyone with link can view", and updates ml_models.drive_file_id in the DB.

Requires Google OAuth credentials (token.json / credentials.json at project root).
Uses the same Google API already configured in .env.

Input JSON (--input or --input-file):
{
  "db_path": ".tmp/wat_genomics.db",
  "model_id": "uuid-of-trained-model",
  "drive_folder_id": "optional-google-drive-folder-id",
  "folder_name": "WAT_ML_Models",         // used if drive_folder_id not supplied
  "create_folder_if_missing": true
}

Output JSON:
{
  "status": "ok",
  "model_id": "uuid",
  "drive_file_id": "1a2b3c...",
  "drive_url": "https://drive.google.com/file/d/1a2b3c.../view",
  "file_size_mb": 12.4,
  "folder_id": "..."
}
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
from googleapiclient.http import MediaFileUpload

load_dotenv()

DEFAULT_DB = ".tmp/wat_genomics.db"
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


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


def find_or_create_folder(drive_svc, folder_name: str,
                           parent_id: str = None) -> str:
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = drive_svc.files().list(q=query, fields="files(id,name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]

    # Create folder
    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = drive_svc.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_file(drive_svc, local_path: str, folder_id: str) -> dict:
    file_name = Path(local_path).name
    file_size = Path(local_path).stat().st_size

    media = MediaFileUpload(
        local_path,
        mimetype="application/octet-stream",
        resumable=True,
    )

    metadata = {
        "name": file_name,
        "parents": [folder_id],
    }

    # Check if a file with the same name exists (replace it)
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    existing = drive_svc.files().list(q=query, fields="files(id)").execute()
    existing_items = existing.get("files", [])

    if existing_items:
        file_id = existing_items[0]["id"]
        result = drive_svc.files().update(
            fileId=file_id, media_body=media, fields="id,name,size"
        ).execute()
    else:
        result = drive_svc.files().create(
            body=metadata, media_body=media, fields="id,name,size"
        ).execute()

    return {
        "file_id": result["id"],
        "file_name": result.get("name", file_name),
        "size_bytes": file_size,
        "size_mb": round(file_size / (1024 * 1024), 2),
    }


def share_file(drive_svc, file_id: str) -> str:
    drive_svc.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()
    return f"https://drive.google.com/file/d/{file_id}/view"


def load_model_meta(db_path: str, model_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM ml_models WHERE model_id=?", (model_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError(f"model_id '{model_id}' not found in ml_models table")
    return dict(row)


def update_drive_id(db_path: str, model_id: str, drive_file_id: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE ml_models SET drive_file_id=? WHERE model_id=?",
            (drive_file_id, model_id),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Upload trained model to Google Drive")
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

        db_path = spec.get("db_path", DEFAULT_DB)
        model_id = spec.get("model_id")
        if not model_id:
            raise ValueError("'model_id' is required")

        model_meta = load_model_meta(db_path, model_id)
        local_path = model_meta.get("local_path")
        if not local_path or not Path(local_path).exists():
            raise FileNotFoundError(f"Model file not found: {local_path}")

        creds = get_credentials()
        drive_svc = build("drive", "v3", credentials=creds)

        folder_id = spec.get("drive_folder_id")
        if not folder_id:
            folder_name = spec.get("folder_name", "WAT_ML_Models")
            create_folder = spec.get("create_folder_if_missing", True)
            if create_folder:
                folder_id = find_or_create_folder(drive_svc, folder_name)
            else:
                raise ValueError(
                    "drive_folder_id not provided and create_folder_if_missing is false"
                )

        print(f"  Uploading {Path(local_path).name} to Google Drive ...", file=sys.stderr)
        upload_info = upload_file(drive_svc, local_path, folder_id)
        drive_file_id = upload_info["file_id"]

        drive_url = share_file(drive_svc, drive_file_id)
        update_drive_id(db_path, model_id, drive_file_id)

        result = {
            "status": "ok",
            "model_id": model_id,
            "model_type": model_meta.get("model_type"),
            "target_variable": model_meta.get("target_variable"),
            "drive_file_id": drive_file_id,
            "drive_url": drive_url,
            "folder_id": folder_id,
            "file_size_mb": upload_info["size_mb"],
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
