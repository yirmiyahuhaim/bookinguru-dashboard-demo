from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import WeeklyPerformance
from ..schemas import WeeklyPerformanceCreate, WeeklyPerformanceOut
from ..auth import require_auth

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/", response_model=List[WeeklyPerformanceOut])
def list_performance(
    hotel_id: int = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    q = db.query(WeeklyPerformance)
    if hotel_id:
        q = q.filter(WeeklyPerformance.hotel_id == hotel_id)
    return q.order_by(WeeklyPerformance.week_start_date.desc()).all()


@router.post("/", response_model=WeeklyPerformanceOut, status_code=201)
def create_performance(
    payload: WeeklyPerformanceCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    perf = WeeklyPerformance(**payload.model_dump())
    db.add(perf)
    db.commit()
    db.refresh(perf)
    return perf
