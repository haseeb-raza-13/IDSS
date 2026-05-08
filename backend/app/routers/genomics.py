import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_current_user
from app.models.requests import GenomicsPipelineRequest, NCBIFetchRequest
from app.models.responses import JobStartedResponse
from app.services.job_manager import JobManager
from app.workers.celery_app import run_genomics_pipeline, run_ncbi_fetch

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_ALLOWED_EXTENSIONS = {".fasta", ".fa", ".fna", ".fastq", ".fq"}


def _safe_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in _ALLOWED_EXTENSIONS


@router.post("/pipeline/start", response_model=JobStartedResponse)
@limiter.limit("10/hour")
async def start_pipeline(
    request: Request,
    files: list[UploadFile] = File(...),
    metadata: str = Form(...),
    _user=Depends(get_current_user),
):
    """
    Launch the full genomics pipeline. Multipart body:
      - files: one or more FASTA/FASTQ files
      - metadata: JSON string (GenomicsPipelineRequest schema)
    Returns a job_id to poll at GET /api/jobs/{job_id}.
    """
    try:
        meta = GenomicsPipelineRequest.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files provided")

    for f in files:
        if not _safe_extension(f.filename or ""):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type: {f.filename}. Allowed: {_ALLOWED_EXTENSIONS}",
            )

    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    upload_dir = job_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    for f in files:
        safe_name = Path(f.filename).name  # strip any path traversal
        dest = upload_dir / safe_name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_paths.append(str(dest))

    JobManager.create("genomics_pipeline", job_dir, job_id=job_id)

    run_genomics_pipeline.apply_async(
        args=[job_id, meta.model_dump(), saved_paths],
        task_id=job_id,
    )
    return JobStartedResponse(job_id=job_id)


@router.post("/sequences/fetch-ncbi", response_model=JobStartedResponse)
async def fetch_ncbi(req: NCBIFetchRequest, _user=Depends(get_current_user)):
    if not req.accessions and not req.search_term:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either accessions or search_term",
        )

    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    JobManager.create("ncbi_fetch", job_dir, job_id=job_id)

    run_ncbi_fetch.apply_async(
        args=[job_id, req.model_dump()],
        task_id=job_id,
    )
    return JobStartedResponse(job_id=job_id)
