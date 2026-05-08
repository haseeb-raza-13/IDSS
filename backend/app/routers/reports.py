from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.config import settings
from app.db import queries
from app.dependencies import get_current_user
from app.services.job_manager import JobManager

router = APIRouter()


def _find_report(run_id: str, filename: str) -> Path:
    """Search all job dirs for a report file associated with a run_id."""
    # Reports are stored in the job dir that produced the run
    # We locate the job by scanning Redis is expensive; instead scan job_tmp_dir
    for job_dir in settings.job_tmp_dir.iterdir():
        candidate = job_dir / filename
        if candidate.exists():
            # Verify this job produced the right run_id
            job = JobManager.get(job_dir.name)
            if job and job.get("run_id") == run_id:
                return candidate
    raise FileNotFoundError(f"Report not found for run {run_id}")


@router.get("/runs/{run_id}/genomics.docx")
async def download_genomics_report(run_id: str, _user=Depends(get_current_user)):
    run = queries.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    try:
        path = _find_report(run_id, "genomics_report.docx")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not yet generated")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"genomics_report_{run_id[:8]}.docx",
    )


@router.get("/runs/{run_id}/alert.docx")
async def download_alert_report(run_id: str, _user=Depends(get_current_user)):
    run = queries.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    try:
        path = _find_report(run_id, "alert_report.docx")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert report not yet generated")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"alert_report_{run_id[:8]}.docx",
    )
