import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


# ── Fixtures: temporary file system ────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_root(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("idss_test")


@pytest.fixture(scope="session")
def test_db_path(tmp_root) -> Path:
    db = tmp_root / "test.db"
    conn = sqlite3.connect(str(db))
    _init_test_schema(conn)
    conn.close()
    return db


def _init_test_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            researcher TEXT,
            study_name TEXT,
            pathogen TEXT,
            source_type TEXT DEFAULT 'unknown',
            country TEXT,
            region TEXT,
            facility TEXT,
            notes TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS samples (
            sample_id TEXT PRIMARY KEY,
            run_id TEXT,
            file_path TEXT,
            format TEXT
        );
        CREATE TABLE IF NOT EXISTS qc_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,
            contig_count INTEGER,
            total_length INTEGER,
            gc_pct REAL,
            n_content_pct REAL,
            n50 INTEGER,
            qc_pass INTEGER
        );
        CREATE TABLE IF NOT EXISTS amr_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT
        );
        CREATE TABLE IF NOT EXISTS amr_hits (
            hit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER,
            gene TEXT,
            drug_class TEXT,
            identity REAL
        );
        CREATE TABLE IF NOT EXISTS snp_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,
            snp_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS snp_variants (
            variant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER,
            position INTEGER,
            ref_allele TEXT,
            alt_allele TEXT
        );
        CREATE TABLE IF NOT EXISTS phylo_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            newick TEXT,
            method TEXT
        );
        CREATE TABLE IF NOT EXISTS phenotypic_samples (
            sample_id TEXT PRIMARY KEY,
            pathogen_name TEXT,
            region TEXT,
            facility TEXT,
            collection_date TEXT
        );
        CREATE TABLE IF NOT EXISTS ast_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,
            antibiotic TEXT,
            interpretation TEXT,
            mic REAL
        );
        CREATE TABLE IF NOT EXISTS mdr_classifications (
            class_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,
            mdr_class TEXT
        );
        CREATE TABLE IF NOT EXISTS alert_records (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            alert_level TEXT,
            alert_score INTEGER,
            triggers TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ml_models (
            model_id TEXT PRIMARY KEY,
            model_type TEXT,
            target_variable TEXT,
            feature_set TEXT,
            accuracy REAL,
            auc_roc REAL,
            f1_score REAL,
            sample_count INTEGER,
            local_path TEXT,
            drive_url TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ml_predictions (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT,
            sample_id TEXT,
            prediction TEXT,
            confidence REAL,
            created_at TEXT
        );
        """
    )
    conn.commit()


# ── Fixtures: FastAPI app with overrides ───────────────────────────────────

@pytest.fixture(scope="session")
def app(test_db_path, tmp_root):
    from app.config import settings

    settings.db_path = test_db_path
    settings.job_tmp_dir = tmp_root / "jobs"
    settings.job_tmp_dir.mkdir(exist_ok=True)
    settings.redis_url = "redis://localhost:6379/15"  # test DB slot

    from app.main import app as _app
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Fixtures: auth token ────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def auth_headers(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)

    c.post("/auth/register", json={"email": "test@idss.test", "password": "testpass1", "name": "Tester"})
    resp = c.post("/auth/login", json={"email": "test@idss.test", "password": "testpass1"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures: mocked ToolRunner ─────────────────────────────────────────────

@pytest.fixture
def mock_tool_runner():
    from app.services.tool_runner import ToolResult

    runner = MagicMock()
    runner.run_tool.return_value = ToolResult(status="ok", data={"test": True})
    return runner


# ── Fixtures: fake FASTA file ───────────────────────────────────────────────

@pytest.fixture
def sample_fasta(tmp_path) -> Path:
    fa = tmp_path / "test.fasta"
    fa.write_text(">seq1\nATGCATGCATGC\n>seq2\nGCATGCATGCAT\n")
    return fa
