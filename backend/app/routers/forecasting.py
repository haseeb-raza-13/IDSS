import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.dependencies import get_current_user
from app.models.requests import ForecastRequest
from app.models.responses import JobStartedResponse
from app.services.job_manager import JobManager
from app.workers.celery_app import run_forecast

router = APIRouter()


@router.post("/", response_model=JobStartedResponse)
async def forecast(req: ForecastRequest, _user=Depends(get_current_user)):
    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    JobManager.create("forecast", job_dir, job_id=job_id)

    run_forecast.apply_async(args=[job_id, req.model_dump()], task_id=job_id)
    return JobStartedResponse(job_id=job_id)
