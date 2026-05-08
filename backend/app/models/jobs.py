from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class JobStep(BaseModel):
    name: str
    status: str  # pending | running | done | failed
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    type: str
    status: str  # pending | running | done | failed
    steps: list[JobStep] = []
    run_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
