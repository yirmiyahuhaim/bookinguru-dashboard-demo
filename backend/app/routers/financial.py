from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from collections import defaultdict
from datetime import date, datetime
from ..database import get_db
from ..models import FinancialSnapshot, Hotel, WeeklyPerformance, DailyBooking
from ..schemas import (
    FinancialSnapshotCreate, FinancialSnapshotOut,
    PortfolioSummary, PortfolioTrendPoint, MonthlyAttachRatePoint,
    VendorStat, ProductStat,
)
from ..services.kpi_engine import get_portfolio_summary, get_portfolio_trend, _active_hotel_classes
from ..auth import require_auth, require_internal_auth

router = APIRouter(prefix="/financial", tags=["financial"])


class InternalMetrics(BaseModel):
    cash_balance: Optional[float] = None
    runway_months: Optional[float] = None
    monthly_burn_rate: Optional[float] = None


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(
    market: Optional[str] = None,
    property_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = get_portfolio_summary(
        db, market=market, property_type=property_type, status=status,
        date_from=date_from, date_to=date_to,
    )
    # Sensitive fields are withheld from the public summary endpoint.
    # Fetch them separately via /financial/internal-metrics.
    result.cash_balance    = None
    result.runway_months   = None
    result.monthly_burn_rate = None
    return result


@router.get("/internal-metrics", response_model=InternalMetrics)
def internal_metrics(
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
    __: str = Depends(require_internal_auth),
):
    """
    Returns Cash Balance, Runway, and Burn Rate.
    Requires both investor auth (HTTP Basic) AND the internal token
    (X-Internal-Token header).  Set INTERNAL_PASS in Render env vars.
    """
    snapshot = db.query(FinancialSnapshot).order_by(
        FinancialSnapshot.snapshot_date.desc()
    ).first()
    if not snapshot:
        return InternalMetrics()
    return InternalMetrics(
        cash_balance=snapshot.cash_balance,
        runway_months=snapshot.runway_months,
        monthly_burn_rate=snapshot.monthly_burn_rate,
    )


@router.get("/attach-rate-monthly", response_model=List[MonthlyAttachRatePoint])
def attach_rate_monthly(
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    market:        Optional[str] = None,
    property_type: Optional[str] = None,
    status:        Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Monthly attach-rate breakdown by hotel class (A / A+B / A+B+C),
    computed from the raw daily_bookings table.
    """
    # Hotels matching any active filters
    q = db.query(Hotel)
    if market:        q = q.filter(Hotel.market == market)
    if property_type: q = q.filter(Hotel.property_type == property_type)
    if status:        q = q.filter(Hotel.pipeline_status == status)
    hotels = q.all()
    hotel_ids = [h.id for h in hotels]
    if not hotel_ids:
        return []

    hotel_room_map = {h.id: (h.room_count or 0) for h in hotels}

    # Classify hotels using WeeklyPerformance (consistent with weekly view)
    all_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    ).all()
    if not all_perfs:
        return []

    max_week_q = db.query(func.max(WeeklyPerformance.week_start_date)).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    )
    if date_from: max_week_q = max_week_q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   max_week_q = max_week_q.filter(WeeklyPerformance.week_start_date <= date_to)
    data_max_week = max_week_q.scalar() or max(p.week_start_date for p in all_perfs)

    hotel_classes = _active_hotel_classes(all_perfs, data_max_week)
    a_ids   = {hid for hid, cls in hotel_classes.items() if cls == "A"}
    ab_ids  = {hid for hid, cls in hotel_classes.items() if cls in ("A", "B")}
    abc_ids = set(hotel_classes.keys())

    if not abc_ids:
        return []

    rooms_a   = sum(hotel_room_map.get(hid, 0) for hid in a_ids)
    rooms_ab  = sum(hotel_room_map.get(hid, 0) for hid in ab_ids)
    rooms_abc = sum(hotel_room_map.get(hid, 0) for hid in abc_ids)

    # Name → id map to resolve bookings where hotel_id was not set during sync
    hotel_name_to_id = {h.name.lower().strip(): h.id for h in hotels if h.id in abc_ids}
    abc_names = list({h.name for h in hotels if h.id in abc_ids})

    # Query daily bookings — match by hotel_id OR by hotel_name_raw (for NULL hotel_ids)
    from sqlalchemy import or_, and_, func as sqlfunc
    bq = db.query(DailyBooking).filter(
        or_(
            DailyBooking.hotel_id.in_(list(abc_ids)),
            and_(
                DailyBooking.hotel_id.is_(None),
                sqlfunc.lower(DailyBooking.hotel_name_raw).in_(
                    [n.lower() for n in abc_names]
                ),
            ),
        )
    )
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)
    # Keep rows where status is null OR not 'Cancelled'
    from sqlalchemy import or_ as or2
    bq = bq.filter(
        or2(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        )
    )
    bookings = bq.all()

    # Group by month × effective hotel_id (resolve NULL hotel_ids via name map)
    monthly_hotel_txns: dict = defaultdict(lambda: defaultdict(int))
    for b in bookings:
        eid = b.hotel_id
        if eid is None and b.hotel_name_raw:
            eid = hotel_name_to_id.get(b.hotel_name_raw.lower().strip())
        if eid is None:
            continue
        monthly_hotel_txns[b.reservation_date.strftime('%Y-%m')][eid] += 1

    result = []
    for month_key in sorted(monthly_hotel_txns.keys()):
        htxns = monthly_hotel_txns[month_key]
        txns_a   = sum(htxns.get(hid, 0) for hid in a_ids)
        txns_ab  = sum(htxns.get(hid, 0) for hid in ab_ids)
        txns_abc = sum(htxns.get(hid, 0) for hid in abc_ids)
        dt = datetime.strptime(month_key + '-01', '%Y-%m-%d')
        result.append(MonthlyAttachRatePoint(
            month=month_key,
            label=dt.strftime("%b '%y"),
            attach_rate_a=   round(txns_a   / rooms_a   * 100, 2) if rooms_a   else 0.0,
            attach_rate_ab=  round(txns_ab  / rooms_ab  * 100, 2) if rooms_ab  else 0.0,
            attach_rate_abc= round(txns_abc / rooms_abc * 100, 2) if rooms_abc else 0.0,
            txns_a=txns_a, txns_ab=txns_ab, txns_abc=txns_abc,
        ))
    return result


@router.get("/portfolio-trend", response_model=List[PortfolioTrendPoint])
def portfolio_trend(
    market: Optional[str] = None,
    property_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    return get_portfolio_trend(
        db, market=market, property_type=property_type, status=status,
        date_from=date_from, date_to=date_to,
    )


@router.get("/snapshots", response_model=List[FinancialSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    return db.query(FinancialSnapshot).order_by(
        FinancialSnapshot.snapshot_date.desc()
    ).limit(52).all()


@router.post("/snapshots", response_model=FinancialSnapshotOut, status_code=201)
def create_snapshot(
    payload: FinancialSnapshotCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    snap = FinancialSnapshot(**payload.model_dump())
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


@router.get("/top-vendors", response_model=List[VendorStat])
def top_vendors(
    limit: int = 10,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    hotel_id:      Optional[int] = None,
    market:        Optional[str] = None,
    property_type: Optional[str] = None,
    status:        Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Top vendors (Column Q) by booking count from daily_bookings."""
    from sqlalchemy import or_
    bq = db.query(
        DailyBooking.company_name,
        func.count().label("bookings"),
        func.sum(DailyBooking.total_paid).label("gmv"),
    ).filter(
        DailyBooking.company_name.isnot(None),
        DailyBooking.company_name != "",
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)
    # Scope to a single hotel when hotel_id is provided
    if hotel_id is not None:
        bq = bq.filter(DailyBooking.hotel_id == hotel_id)
    # Otherwise optionally scope to hotels matching portfolio filters
    elif market or property_type or status:
        hq = db.query(Hotel.id)
        if market:        hq = hq.filter(Hotel.market == market)
        if property_type: hq = hq.filter(Hotel.property_type == property_type)
        if status:        hq = hq.filter(Hotel.pipeline_status == status)
        hotel_ids = [r[0] for r in hq.all()]
        if not hotel_ids:
            return []
        bq = bq.filter(DailyBooking.hotel_id.in_(hotel_ids))

    rows = (
        bq.group_by(DailyBooking.company_name)
          .order_by(func.count().desc())
          .limit(limit)
          .all()
    )
    return [VendorStat(vendor=r[0], bookings=r[1], gmv=round(r[2] or 0, 2)) for r in rows]


@router.get("/vendor-weekly")
def vendor_weekly(
    hotel_id: int,
    limit: int = 5,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Weekly booking counts per top vendor for a single hotel — for stacked bar chart."""
    from sqlalchemy import or_
    from datetime import timedelta
    from collections import defaultdict as _dd
    bq = db.query(DailyBooking).filter(
        DailyBooking.hotel_id == hotel_id,
        DailyBooking.company_name.isnot(None),
        DailyBooking.company_name != "",
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)
    bookings = bq.all()

    if not bookings:
        return {"vendors": [], "weeks": []}

    vendor_totals: dict = _dd(int)
    for b in bookings:
        vendor_totals[b.company_name] += 1
    top_vendors = [v for v, _ in sorted(vendor_totals.items(), key=lambda x: -x[1])[:limit]]

    week_data: dict = _dd(lambda: _dd(int))
    for b in bookings:
        if b.company_name not in top_vendors:
            continue
        rd = b.reservation_date
        week_start = str(rd - timedelta(days=rd.weekday()))
        week_data[week_start][b.company_name] += 1

    weeks = [
        {"week": w, **{v: week_data[w].get(v, 0) for v in top_vendors}}
        for w in sorted(week_data.keys())
    ]
    return {"vendors": top_vendors, "weeks": weeks}


@router.get("/vendor-hotels")
def vendor_hotels(
    vendor: str,
    limit: int = 5,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Top hotels for a given vendor by booking count."""
    from sqlalchemy import or_
    bq = db.query(
        DailyBooking.hotel_name_raw,
        func.count().label("bookings"),
        func.sum(DailyBooking.total_paid).label("gmv"),
    ).filter(
        DailyBooking.company_name == vendor,
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)
    rows = (
        bq.group_by(DailyBooking.hotel_name_raw)
          .order_by(func.count().desc())
          .limit(limit)
          .all()
    )
    return [{"hotel": r[0], "bookings": r[1], "gmv": round(r[2] or 0, 2)} for r in rows]


@router.get("/vendor-weekly-performance")
def vendor_weekly_performance(
    vendor: str,
    hotel_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Weekly booking count and GMV for a specific vendor — across all hotels,
    or scoped to one hotel when hotel_id is given. Each week also carries the
    same-week-last-season figures (364 days back, preserves day-of-week
    alignment) so the caller can render a year-over-year comparison.
    """
    from sqlalchemy import or_
    from datetime import timedelta

    bq = db.query(DailyBooking).filter(
        DailyBooking.company_name == vendor,
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if hotel_id is not None:
        bq = bq.filter(DailyBooking.hotel_id == hotel_id)

    # Fetch full history (unfiltered by date) so "same week last season" can
    # be looked up even when it falls outside the requested range.
    all_bookings = bq.all()
    if not all_bookings:
        return []

    hist_week_data: dict = {}
    for b in all_bookings:
        rd = b.reservation_date
        week_start = rd - timedelta(days=rd.weekday())
        d = hist_week_data.setdefault(week_start, {"bookings": 0, "gmv": 0.0})
        d["bookings"] += 1
        d["gmv"] += b.total_paid or 0.0

    if date_from or date_to:
        weeks = sorted(
            w for w in hist_week_data
            if (not date_from or w >= date_from) and (not date_to or w <= date_to)
        )
    else:
        weeks = sorted(hist_week_data.keys())

    result = []
    for w in weeks:
        cur = hist_week_data[w]
        prev = hist_week_data.get(w - timedelta(days=364))
        result.append({
            "week": str(w),
            "bookings": cur["bookings"],
            "gmv": round(cur["gmv"], 2),
            "prev_bookings": prev["bookings"] if prev else None,
            "prev_gmv": round(prev["gmv"], 2) if prev else None,
        })
    return result


@router.get("/hotel-weekly-matrix")
def hotel_weekly_matrix(
    market:        Optional[str] = None,
    property_type: Optional[str] = None,
    status:        Optional[str] = None,
    date_from:     Optional[date] = None,
    date_to:       Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Spreadsheet-style matrix: hotels (rows) × weeks (columns), cells =
    weekly paid bookings. Ranked by total bookings in the range. Mirrors the
    'Weekly Counts' tab. Respects the portfolio date range and filters.
    """
    hq = db.query(Hotel)
    if market:        hq = hq.filter(Hotel.market == market)
    if property_type: hq = hq.filter(Hotel.property_type == property_type)
    if status:        hq = hq.filter(Hotel.pipeline_status == status)
    hotels = hq.all()
    hmap = {h.id: h.name for h in hotels}
    if not hmap:
        return {"weeks": [], "rows": []}

    wq = db.query(WeeklyPerformance).filter(WeeklyPerformance.hotel_id.in_(list(hmap.keys())))
    if date_from: wq = wq.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   wq = wq.filter(WeeklyPerformance.week_start_date <= date_to)
    perfs = wq.all()
    if not perfs:
        return {"weeks": [], "rows": []}

    weeks = sorted({p.week_start_date for p in perfs})
    cells: dict  = defaultdict(lambda: defaultdict(int))
    totals: dict = defaultdict(int)
    for p in perfs:
        n = p.transactions or 0
        cells[p.hotel_id][p.week_start_date] += n
        totals[p.hotel_id] += n

    rows = []
    for hid in cells:
        rows.append({
            "hotel_id": hid,
            "hotel":    hmap.get(hid, "Unknown"),
            "total":    totals[hid],
            "weeks":    [cells[hid].get(w, 0) for w in weeks],
        })
    rows.sort(key=lambda r: -r["total"])

    return {"weeks": [w.isoformat() for w in weeks], "rows": rows}


@router.get("/weekly-insights")
def weekly_insights(
    week:      Optional[date] = None,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Week-over-week movers for hotels and vendors — what grew or declined sharply
    vs last week and vs the trailing 4-week average, with a prioritised brief.
    `week` selects a specific week (defaults to latest); date range scopes the
    selectable weeks.
    """
    from ..services.insights_engine import get_weekly_insights
    return get_weekly_insights(db, week=week, date_from=date_from, date_to=date_to)


@router.get("/forecast")
def get_forecast(_: str = Depends(require_auth)):
    """
    Fetch Bookings Forecast and GMV Forecast from the Forecast tab in Google Sheets.
    Data is fetched live (not stored in DB) since it changes infrequently.
    """
    from fastapi import HTTPException
    from ..services.sheets_sync import fetch_forecast_data
    try:
        return fetch_forecast_data()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/top-products")
def top_products(
    limit: int = 10,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    market:        Optional[str] = None,
    property_type: Optional[str] = None,
    status:        Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Top N product+vendor pairs by total bookings, with per-week breakdown.
    Returns {products: [{product, vendor, label, total_bookings, total_gmv}],
             weeks:    [{week, <label>: bookings, <label>_gmv: gmv, ...}]}
    Weeks rows are ordered chronologically; products are ordered by total
    bookings descending so the largest segment renders at the base of each
    stacked bar.
    """
    from sqlalchemy import or_
    from datetime import timedelta

    non_cancelled = or_(
        DailyBooking.reservation_status.is_(None),
        DailyBooking.reservation_status != "Cancelled",
    )

    # Apply optional portfolio scope
    hotel_ids = None
    if market or property_type or status:
        hq = db.query(Hotel.id)
        if market:        hq = hq.filter(Hotel.market == market)
        if property_type: hq = hq.filter(Hotel.property_type == property_type)
        if status:        hq = hq.filter(Hotel.pipeline_status == status)
        hotel_ids = [r[0] for r in hq.all()]
        if not hotel_ids:
            return {"products": [], "weeks": []}

    # Step 1 — rank product+vendor pairs by total bookings in the period
    rank_q = db.query(
        DailyBooking.product_name,
        DailyBooking.company_name,
        func.count().label("total_bookings"),
        func.sum(DailyBooking.total_paid).label("total_gmv"),
    ).filter(
        DailyBooking.product_name.isnot(None),
        DailyBooking.product_name != "",
        DailyBooking.company_name.isnot(None),
        DailyBooking.company_name != "",
        non_cancelled,
    )
    if date_from:   rank_q = rank_q.filter(DailyBooking.reservation_date >= date_from)
    if date_to:     rank_q = rank_q.filter(DailyBooking.reservation_date <= date_to)
    if hotel_ids is not None:
        rank_q = rank_q.filter(DailyBooking.hotel_id.in_(hotel_ids))

    top_rows = (
        rank_q.group_by(DailyBooking.product_name, DailyBooking.company_name)
              .order_by(func.count().desc())
              .limit(limit)
              .all()
    )
    if not top_rows:
        return {"products": [], "weeks": []}

    # Build a label key and an ordered product list (largest → smallest)
    def make_label(product, vendor):
        return f"{product} · {vendor}"

    products_meta = [
        {
            "product": r[0],
            "vendor": r[1],
            "label": make_label(r[0], r[1]),
            "total_bookings": r[2],
            "total_gmv": round(r[3] or 0, 2),
        }
        for r in top_rows
    ]
    top_labels = {p["label"] for p in products_meta}
    label_of = {(p["product"], p["vendor"]): p["label"] for p in products_meta}

    # Step 2 — fetch all bookings for those products to build weekly rows
    detail_q = db.query(DailyBooking).filter(
        DailyBooking.product_name.in_([p["product"] for p in products_meta]),
        DailyBooking.company_name.in_([p["vendor"] for p in products_meta]),
        non_cancelled,
    )
    if date_from:   detail_q = detail_q.filter(DailyBooking.reservation_date >= date_from)
    if date_to:     detail_q = detail_q.filter(DailyBooking.reservation_date <= date_to)
    if hotel_ids is not None:
        detail_q = detail_q.filter(DailyBooking.hotel_id.in_(hotel_ids))
    bookings = detail_q.all()

    # Aggregate by (week_start, label)
    week_agg: dict = defaultdict(lambda: defaultdict(lambda: {"bookings": 0, "gmv": 0.0}))
    for b in bookings:
        lbl = label_of.get((b.product_name, b.company_name))
        if lbl not in top_labels:
            continue
        rd = b.reservation_date
        week_start = str(rd - timedelta(days=rd.weekday()))
        week_agg[week_start][lbl]["bookings"] += 1
        week_agg[week_start][lbl]["gmv"] += b.total_paid or 0.0

    # Build flat week rows
    weeks = []
    for w in sorted(week_agg.keys()):
        row: dict = {"week": w}
        for lbl in top_labels:
            agg = week_agg[w].get(lbl, {"bookings": 0, "gmv": 0.0})
            row[lbl] = agg["bookings"]
            row[f"{lbl}_gmv"] = round(agg["gmv"], 2)
        weeks.append(row)

    return {"products": products_meta, "weeks": weeks}


@router.get("/product-weekly-performance")
def product_weekly_performance(
    product: str,
    vendor:   Optional[str] = None,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Weekly bookings and GMV for a specific product (optionally scoped to one vendor)."""
    from sqlalchemy import or_
    from datetime import timedelta

    bq = db.query(DailyBooking).filter(
        DailyBooking.product_name == product,
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if vendor:    bq = bq.filter(DailyBooking.company_name == vendor)
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)
    bookings = bq.all()

    if not bookings:
        return []

    week_data: dict = {}
    for b in bookings:
        rd = b.reservation_date
        week_start = str(rd - timedelta(days=rd.weekday()))
        if week_start not in week_data:
            week_data[week_start] = {"bookings": 0, "gmv": 0.0}
        week_data[week_start]["bookings"] += 1
        week_data[week_start]["gmv"] += b.total_paid or 0.0

    return [
        {"week": w, "bookings": d["bookings"], "gmv": round(d["gmv"], 2)}
        for w, d in sorted(week_data.items())
    ]


@router.get("/vendor-products", response_model=List[ProductStat])
def vendor_products(
    vendor: str,
    limit: int = 5,
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Top products (Column D) for a given vendor, by booking count."""
    from sqlalchemy import or_
    bq = db.query(
        DailyBooking.product_name,
        func.count().label("bookings"),
        func.sum(DailyBooking.total_paid).label("gmv"),
    ).filter(
        DailyBooking.company_name == vendor,
        DailyBooking.product_name.isnot(None),
        DailyBooking.product_name != "",
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    if date_from: bq = bq.filter(DailyBooking.reservation_date >= date_from)
    if date_to:   bq = bq.filter(DailyBooking.reservation_date <= date_to)

    rows = (
        bq.group_by(DailyBooking.product_name)
          .order_by(func.count().desc())
          .limit(limit)
          .all()
    )
    return [ProductStat(product=r[0], bookings=r[1], gmv=round(r[2] or 0, 2)) for r in rows]


