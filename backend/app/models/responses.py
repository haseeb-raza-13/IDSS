from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str


class JobStartedResponse(BaseModel):
    job_id: str
    message: str = "Job queued"


class PipelineRunSummary(BaseModel):
    run_id: str
    researcher: str
    study_name: str
    pathogen: str
    region: Optional[str]
    source_type: str
    sample_count: int
    created_at: datetime
    alert_level: Optional[str] = None
    alert_score: Optional[int] = None


class PipelineRunDetail(BaseModel):
    run_id: str
    researcher: str
    study_name: str
    pathogen: str
    region: Optional[str]
    facility: Optional[str]
    source_type: str
    notes: Optional[str]
    created_at: datetime
    samples: list[dict[str, Any]] = []
    qc_results: list[dict[str, Any]] = []
    amr_results: list[dict[str, Any]] = []
    alert: Optional[dict[str, Any]] = None


class AMRTrendPoint(BaseModel):
    date: str
    gene: str
    region: str
    count: int


class ResistanceRatePoint(BaseModel):
    antibiotic: str
    region: str
    resistance_pct: float
    total_samples: int


class MLModelSummary(BaseModel):
    model_id: str
    model_type: str
    target_variable: str
    feature_set: str
    accuracy: Optional[float]
    auc_roc: Optional[float]
    f1_score: Optional[float]
    sample_count: int
    created_at: datetime
    local_path: Optional[str]
    drive_url: Optional[str]


class AlertSummary(BaseModel):
    alert_id: int
    run_id: str
    alert_level: str
    alert_score: int
    pathogen: Optional[str]
    region: Optional[str]
    triggers: list[str]
    created_at: datetime


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int
