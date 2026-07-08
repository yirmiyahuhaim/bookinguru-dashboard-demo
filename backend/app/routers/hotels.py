from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from ..database import get_db
from ..models import Hotel
from ..schemas import HotelOut, HotelCreate, HotelKPIs, HotelDetailOut
from ..services.kpi_engine import get_hotel_kpis, get_hotel_trend
from ..auth import require_auth

router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.get("/", response_model=List[HotelKPIs])
def list_hotels(
    market: Optional[str] = None,
    property_type: Optional[str] = None,
    status: Optional[str] = None,
    is_alsabini: Optional[bool] = None,
    booking_active: Optional[bool] = None,  # kept for backward compat
    activity_class: Optional[str] = None,   # "A", "B", "C", or "inactive"
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    query = db.query(Hotel)
    if market:
        query = query.filter(Hotel.market == market)
    if property_type:
        query = query.filter(Hotel.property_type == property_type)
    if status:
        query = query.filter(Hotel.pipeline_status == status)
    if is_alsabini is not None:
        query = query.filter(Hotel.is_alsabini == is_alsabini)
    hotels = query.all()
    results = [get_hotel_kpis(db, h, date_from=date_from, date_to=date_to) for h in hotels]
    # booking_active kept for backward compat — filters by is_active
    if booking_active is not None:
        results = [r for r in results if r.is_active == booking_active]
    # activity_class: "A", "B", "C" filters by class; "inactive" filters by not active
    if activity_class:
        if activity_class == "inactive":
            results = [r for r in results if not r.is_active]
        else:
            results = [r for r in results if r.activity_class == activity_class]
    return results


@router.get("/{hotel_id}", response_model=HotelDetailOut)
def get_hotel(
    hotel_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
    kpis = get_hotel_kpis(db, hotel, date_from=date_from, date_to=date_to)
    trend = get_hotel_trend(db, hotel_id, date_from=date_from, date_to=date_to)
    hotel_out = HotelOut.model_validate(hotel)
    return HotelDetailOut(hotel=hotel_out, kpis=kpis, trend=trend)


@router.post("/", response_model=HotelOut, status_code=201)
def create_hotel(
    payload: HotelCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    hotel = Hotel(**payload.model_dump())
    db.add(hotel)
    db.commit()
    db.refresh(hotel)
    return hotel


@router.patch("/{hotel_id}", response_model=HotelOut)
def update_hotel(
    hotel_id: int,
    payload: HotelCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    hotel = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(hotel, k, v)
    db.commit()
    db.refresh(hotel)
    return hotel


@router.get("/meta/filters")
def get_filter_options(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    hotels = db.query(Hotel).all()
    _clean = lambda vals: sorted(v for v in set(vals) if v and v not in ("Unknown", "None"))
    return {
        "markets":        _clean(h.market         for h in hotels),
        "property_types": _clean(h.property_type  for h in hotels),
        "statuses":       _clean(h.pipeline_status for h in hotels),
    }
