from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GenomicsPipelineRequest(BaseModel):
    researcher: str
    study_name: str
    pathogen: str
    source_type: Literal["human", "animal", "environment", "unknown"] = "unknown"
    country: Optional[str] = None
    region: Optional[str] = None
    facility: Optional[str] = None
    notes: Optional[str] = None
    reference_accession: Optional[str] = None
    identity_threshold: float = 0.80
    tree_method: Literal["nj", "upgma"] = "nj"
    kmer_size: int = 21


class NCBIFetchRequest(BaseModel):
    accessions: Optional[list[str]] = None
    search_term: Optional[str] = None
    max_records: int = 10
    database: Literal["nucleotide", "assembly"] = "nucleotide"


class MLTrainRequest(BaseModel):
    model_type: Literal["random_forest", "xgboost", "ann"]
    target_variable: str
    feature_set: Literal["genomic", "phenotypic", "combined"] = "genomic"
    pathogen: Optional[str] = None
    region: Optional[str] = None
    k_folds: int = 5
    rf_n_estimators: int = 200


class ForecastRequest(BaseModel):
    forecast_type: Literal["resistance_rate", "mdr_rate", "gene_frequency"]
    antibiotic: Optional[str] = None
    gene: Optional[str] = None
    region: Optional[str] = None
    pathogen: Optional[str] = None
    days_back: int = 730
    forecast_horizon_months: int = 6


class AlertScoreRequest(BaseModel):
    run_id: str


class AlertReportRequest(BaseModel):
    run_id: str


class PhenotypicIngestMeta(BaseModel):
    study_name: Optional[str] = None
    facility: Optional[str] = None
    region: Optional[str] = None
    notes: Optional[str] = None
