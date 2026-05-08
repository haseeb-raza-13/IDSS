from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    tools_dir: Path = Path(__file__).resolve().parents[2] / "tools"
    db_path: Path = Path(__file__).resolve().parents[2] / ".tmp" / "wat_genomics.db"
    job_tmp_dir: Path = Path("/tmp/idss_jobs")
    credentials_path: Path = Path(__file__).resolve().parents[2] / "credentials.json"
    token_path: Path = Path(__file__).resolve().parents[2] / "token.json"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # NCBI
    ncbi_email: str = ""
    ncbi_api_key: str = ""

    # Google
    google_redirect_uri: str = "http://localhost:8000/api/integrations/google/callback"

    # Anthropic
    anthropic_api_key: str = ""

    # App
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    job_max_age_hours: int = 48


settings = Settings()
