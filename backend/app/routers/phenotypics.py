import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.config import settings
from app.db import queries
from app.dependencies import get_current_user
from app.models.responses import JobStartedResponse
from app.services.job_manager import JobManager
from app.workers.celery_app import run_phenotypic_ingest

router = APIRouter()

_ALLOWED = {".csv", ".xlsx", ".xls"}


@router.post("/ingest", response_model=JobStartedResponse)
async def ingest_ast(
    file: UploadFile = File(...),
    study_name: Optional[str] = Form(None),
    facility: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    _user=Depends(get_current_user),
):
    if Path(file.filename or "").suffix.lower() not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type. Allowed: {_ALLOWED}",
        )

    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest = job_dir / safe_name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    JobManager.create("phenotypic_ingest", job_dir, job_id=job_id)

    run_phenotypic_ingest.apply_async(
        args=[job_id, str(dest), {"study_name": study_name, "facility": facility, "region": region}],
        task_id=job_id,
    )
    return JobStartedResponse(job_id=job_id)


@router.get("/resistance-rates")
async def resistance_rates(
    antibiotic: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    pathogen: Optional[str] = Query(None),
    _user=Depends(get_current_user),
):
    return queries.get_resistance_rates(antibiotic=antibiotic, region=region, pathogen=pathogen)


@router.get("/mdr-trend")
async def mdr_trend(
    region: Optional[str] = Query(None),
    pathogen: Optional[str] = Query(None),
    days: int = Query(365, ge=30),
    _user=Depends(get_current_user),
):
    return queries.get_mdr_trend(region=region, pathogen=pathogen, days=days)
