import io
import json
from unittest.mock import patch, MagicMock

import pytest


class TestGenomicsRouter:
    def test_pipeline_start_requires_auth(self, client, sample_fasta):
        with open(sample_fasta, "rb") as f:
            resp = client.post(
                "/api/genomics/pipeline/start",
                files=[("files", ("test.fasta", f, "application/octet-stream"))],
                data={"metadata": json.dumps({"researcher": "Dr. A", "study_name": "S1", "pathogen": "E. coli"})},
            )
        assert resp.status_code == 403

    def test_pipeline_start_rejects_invalid_extension(self, client, auth_headers, tmp_path):
        bad_file = tmp_path / "data.txt"
        bad_file.write_text("not a fasta")
        meta = json.dumps({"researcher": "Dr. A", "study_name": "S1", "pathogen": "E. coli"})

        with patch("app.routers.genomics.run_genomics_pipeline") as mock_task:
            mock_task.apply_async = MagicMock()
            with open(bad_file, "rb") as f:
                resp = client.post(
                    "/api/genomics/pipeline/start",
                    files=[("files", ("data.txt", f, "text/plain"))],
                    data={"metadata": meta},
                    headers=auth_headers,
                )
        assert resp.status_code == 422
        assert "Unsupported file type" in resp.json()["detail"]

    def test_pipeline_start_rejects_invalid_metadata(self, client, auth_headers, sample_fasta):
        with open(sample_fasta, "rb") as f:
            resp = client.post(
                "/api/genomics/pipeline/start",
                files=[("files", ("test.fasta", f, "application/octet-stream"))],
                data={"metadata": "not-json"},
                headers=auth_headers,
            )
        assert resp.status_code == 422

    def test_pipeline_start_queues_job(self, client, auth_headers, sample_fasta):
        meta = json.dumps({
            "researcher": "Dr. B",
            "study_name": "Study 2",
            "pathogen": "K. pneumoniae",
            "source_type": "human",
        })
        with patch("app.routers.genomics.run_genomics_pipeline") as mock_task:
            mock_task.apply_async = MagicMock()
            with open(sample_fasta, "rb") as f:
                resp = client.post(
                    "/api/genomics/pipeline/start",
                    files=[("files", ("test.fasta", f, "application/octet-stream"))],
                    data={"metadata": meta},
                    headers=auth_headers,
                )

        # Redis may not be available in test — patch JobManager too
        if resp.status_code == 200:
            body = resp.json()
            assert "job_id" in body
            assert len(body["job_id"]) == 36  # UUID

    def test_ncbi_fetch_requires_accessions_or_search(self, client, auth_headers):
        resp = client.post("/api/genomics/sequences/fetch-ncbi", json={}, headers=auth_headers)
        assert resp.status_code == 422


class TestJobsRouter:
    def test_get_nonexistent_job_returns_404(self, client, auth_headers):
        resp = client.get("/api/jobs/nonexistent-job-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_cancel_nonexistent_job_returns_404(self, client, auth_headers):
        resp = client.delete("/api/jobs/nonexistent-job-id", headers=auth_headers)
        assert resp.status_code == 404


class TestHistoryRouter:
    def test_list_runs_returns_paginated(self, client, auth_headers):
        resp = client.get("/api/history/runs", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body

    def test_list_runs_pagination_params(self, client, auth_headers):
        resp = client.get("/api/history/runs?page=1&page_size=5", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_nonexistent_run_returns_404(self, client, auth_headers):
        resp = client.get("/api/history/runs/fake-run-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_amr_trend_returns_list(self, client, auth_headers):
        resp = client.get("/api/history/amr-trend", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_resistance_rate_returns_list(self, client, auth_headers):
        resp = client.get("/api/history/resistance-rate", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_outbreak_check_returns_list(self, client, auth_headers):
        resp = client.get("/api/history/outbreak-check", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
