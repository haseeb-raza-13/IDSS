import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.db import queries
from app.dependencies import get_current_user
from app.models.requests import MLTrainRequest
from app.models.responses import JobStartedResponse
from app.services.job_manager import JobManager
from app.services.tool_runner import ToolRunner
from app.workers.celery_app import run_ml_train

router = APIRouter()


@router.get("/models")
async def list_models(_user=Depends(get_current_user)):
    return queries.list_ml_models()


@router.post("/train", response_model=JobStartedResponse)
async def train_model(req: MLTrainRequest, _user=Depends(get_current_user)):
    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    JobManager.create("ml_train", job_dir, job_id=job_id)

    run_ml_train.apply_async(
        args=[job_id, req.model_dump()],
        task_id=job_id,
    )
    return JobStartedResponse(job_id=job_id)


@router.post("/predict")
async def predict(model_id: str, run_id: str, _user=Depends(get_current_user)):
    runner = ToolRunner()
    job_id = str(uuid.uuid4())
    job_dir = settings.job_tmp_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    result = runner.run_tool(
        "ml_predict",
        {"model_id": model_id, "run_id": run_id, "db_path": str(settings.db_path)},
        job_dir,
    )
    if result.status == "error":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)
    return result.data


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: str, _user=Depends(get_current_user)):
    from app.db.connection import db_cursor
    with db_cursor() as cur:
        row = cur.execute("SELECT local_path FROM ml_models WHERE model_id = ?", (model_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        local_path = row["local_path"]
        cur.execute("DELETE FROM ml_predictions WHERE model_id = ?", (model_id,))
        cur.execute("DELETE FROM ml_models WHERE model_id = ?", (model_id,))

    if local_path:
        from pathlib import Path
        p = Path(local_path)
        if p.exists():
            p.unlink()
