import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.db import queries
from app.dependencies import get_current_user
from app.models.requests import AlertScoreRequest
from app.models.responses import JobStartedResponse
from app.services.job_manager import JobManager
from app.workers.celery_app import run_alert_score

router = APIRouter()


@router.get("/")
async def list_alerts(
    level: Optional[str] = Query(None, pattern="^(RED|ORANGE|YELLOW|GREEN)$"),
    region: Optional[str] = Query(None),
    days: int = Query(90, ge=1, le=3650),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    return queries.list_alerts(level=level, region=region, days=days, page=page, page_size=page_size)


@router.post("/score", response_model=JobStartedResponse)
async def score_alert(req: AlertScoreRequest, _user=Depends(get_current_user)):
    # Verify run exists
    run = queries.get_run_detail(req.run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    JobManager.create("alert_score", job_dir, job_id=job_id)

    run_alert_score.apply_async(args=[job_id, req.run_id], task_id=job_id)
    return JobStartedResponse(job_id=job_id)
