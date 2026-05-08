from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db import queries
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/runs")
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    pathogen: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    _user=Depends(get_current_user),
):
    return queries.list_runs(page=page, page_size=page_size, pathogen=pathogen, region=region)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, _user=Depends(get_current_user)):
    detail = queries.get_run_detail(run_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return detail


@router.get("/amr-trend")
async def amr_trend(
    gene: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    days: int = Query(365, ge=30, le=1825),
    _user=Depends(get_current_user),
):
    return queries.get_amr_trend(gene=gene, region=region, days=days)


@router.get("/resistance-rate")
async def resistance_rate(
    antibiotic: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    pathogen: Optional[str] = Query(None),
    _user=Depends(get_current_user),
):
    return queries.get_resistance_rates(antibiotic=antibiotic, region=region, pathogen=pathogen)


@router.get("/outbreak-check")
async def outbreak_check(
    days: int = Query(90, ge=7, le=365),
    min_samples: int = Query(3, ge=2),
    _user=Depends(get_current_user),
):
    return queries.get_outbreak_signals(days=days, min_samples=min_samples)


@router.get("/mdr-trend")
async def mdr_trend(
    region: Optional[str] = Query(None),
    pathogen: Optional[str] = Query(None),
    days: int = Query(365, ge=30),
    _user=Depends(get_current_user),
):
    return queries.get_mdr_trend(region=region, pathogen=pathogen, days=days)
