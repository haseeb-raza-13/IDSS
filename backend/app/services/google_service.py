"""
Server-side Google OAuth flow.

Replaces the run_local_server() approach in sheets_dashboard.py and drive_backup.py,
which cannot work in a containerized/headless environment.

The existing tools still read credentials.json and token.json from the project root
(provided via Docker volume mount), so we write token.json to the same location.
"""
import json
from pathlib import Path
from typing import Optional

from app.config import settings

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleService:
    @staticmethod
    def get_auth_url() -> str:
        from google_auth_oauthlib.flow import Flow

        if not settings.credentials_path.exists():
            raise FileNotFoundError(
                f"credentials.json not found at {settings.credentials_path}. "
                "Download it from Google Cloud Console."
            )

        flow = Flow.from_client_secrets_file(
            str(settings.credentials_path),
            scopes=_SCOPES,
            redirect_uri=settings.google_redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    @staticmethod
    def exchange_code(code: str) -> None:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(settings.credentials_path),
            scopes=_SCOPES,
            redirect_uri=settings.google_redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else _SCOPES,
        }
        settings.token_path.write_text(json.dumps(token_data), encoding="utf-8")

    @staticmethod
    def is_connected() -> bool:
        if not settings.token_path.exists():
            return False
        try:
            data = json.loads(settings.token_path.read_text())
            return bool(data.get("refresh_token") or data.get("token"))
        except (json.JSONDecodeError, OSError):
            return False
