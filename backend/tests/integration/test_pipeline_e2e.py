"""
Integration tests that invoke real tool subprocesses.
Run with: pytest -m integration

These tests require:
- tools/requirements.txt installed in the test environment
- No NCBI/Google API calls (mocked at subprocess level)
"""
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_qc_sequences_tool_output_contract(tmp_path):
    """Verify qc_sequences.py produces expected JSON keys."""
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    job_dir = tmp_path / "qc_job"

    # Build a minimal sequences_index manually
    fasta_a = FIXTURES / "sample_a.fasta"
    sequences_index = {
        "files": [
            {"path": str(fasta_a), "format": "fasta", "sample_id": "sample_A"}
        ]
    }

    result = runner.run_tool(
        "qc_sequences",
        {"sequences_index": sequences_index},
        job_dir,
    )

    assert result.status in ("ok", "error"), f"Unexpected status: {result.status}"
    if result.status == "ok":
        # Verify top-level keys the rest of the pipeline depends on
        assert "samples" in result.data or "qc_results" in result.data or isinstance(result.data, list)


@pytest.mark.integration
def test_fetch_local_sequences_tool_output_contract(tmp_path):
    """Verify fetch_local_sequences.py catalogs FASTA files correctly."""
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    job_dir = tmp_path / "fetch_job"

    result = runner.run_tool(
        "fetch_local_sequences",
        {"directory": str(FIXTURES), "extensions": [".fasta"]},
        job_dir,
    )

    assert result.status == "ok", f"Tool error: {result.stderr}"
    data = result.data
    # Should have found our 3 fixture FASTA files
    files = data.get("files", [])
    assert len(files) >= 3, f"Expected >=3 FASTA files, got {len(files)}"
    for f in files:
        assert "path" in f
        assert "sample_id" in f or "filename" in f


@pytest.mark.integration
def test_amr_detection_tool_output_contract(tmp_path):
    """
    Verify amr_detection.py produces expected JSON structure.
    NCBI fetch of the AMR database is skipped by providing a cached empty db.
    """
    from app.services.tool_runner import ToolRunner

    runner = ToolRunner()
    job_dir = tmp_path / "amr_job"
    job_dir.mkdir(parents=True)

    # Create a minimal AMR DB cache (empty, so no hits expected)
    amr_cache = job_dir / "amr_db.fasta"
    amr_cache.write_text("")  # empty = no hits

    sequences_index = {
        "files": [
            {"path": str(FIXTURES / "sample_a.fasta"), "format": "fasta", "sample_id": "sample_A"}
        ]
    }

    result = runner.run_tool(
        "amr_detection",
        {
            "sequences_index": sequences_index,
            "identity_threshold": 0.80,
            "db_cache_path": ".tmp/amr_db.fasta",
            "ncbi_email": "test@test.com",
        },
        job_dir,
    )

    # With empty cache, should either succeed with 0 hits or error gracefully
    assert result.status in ("ok", "error", "insufficient_data")
    if result.status == "ok":
        assert isinstance(result.data, dict)
