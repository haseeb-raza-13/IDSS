from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.routers import alerts, auth, forecasting, genomics, history, integrations, jobs, ml, phenotypics, reports


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.job_tmp_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="IDSS API",
    description="Integrated Disease Surveillance System — AMR Genomics Pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(genomics.router, prefix="/api/genomics", tags=["genomics"])
app.include_router(phenotypics.router, prefix="/api/phenotypics", tags=["phenotypics"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(ml.router, prefix="/api/ml", tags=["ml"])
app.include_router(forecasting.router, prefix="/api/forecast", tags=["forecast"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])


@app.get("/health")
async def health():
    return {"status": "ok"}
