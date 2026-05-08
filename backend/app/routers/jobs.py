from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.models.jobs import JobStatus
from app.services.job_manager import JobManager

router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str, _user=Depends(get_current_user)):
    job = JobManager.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatus(**job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(job_id: str, _user=Depends(get_current_user)):
    cancelled = JobManager.cancel(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or already completed",
        )
