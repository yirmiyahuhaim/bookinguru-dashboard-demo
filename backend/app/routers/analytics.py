from fastapi import APIRouter, Depends, Query
from ..services.ga4_service import get_ga4_metrics
from ..auth import require_auth

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/ga4")
def ga4_metrics(
    days: int = Query(default=30, ge=7, le=365),
    _: str = Depends(require_auth),
):
    """Return GA4-derived metrics: Click→Purchase Conversion and Direct Session %."""
    return get_ga4_metrics(days=days)
