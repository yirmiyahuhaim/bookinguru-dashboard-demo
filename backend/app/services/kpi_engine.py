import json
import statistics
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from typing import List, Optional, Dict
from collections import defaultdict
from ..models import Hotel, WeeklyPerformance, FinancialSnapshot
from ..schemas import HotelKPIs, PortfolioSummary, HotelTrend, PortfolioTrendPoint

INDUSTRY_CANCELLATION_RATE = 19.0  # Ibiza industry average


# ── Active-hotel rule ────────────────────────────────────────────────────────
#
# On-season  = March–October  (months 3–10)
# Off-season = November–February (months 11–12 of year Y, months 1–2 of Y+1)
#
# A hotel is Active when EITHER:
#   (a) It recorded ≥ 3 bookings in any single on-season month of the
#       *relevant* on-season year, OR
#   (b) It recorded ≥ 1 booking in the most recent 4 data weeks
#       (removes weekly flicker caused by a single quiet week).
#
# "Relevant on-season year" is determined from data_max_week:
#   • Jan–Feb  → previous year  (off-season carry-over from last summer)
#   • Mar–Dec  → current year
#
# This means a hotel that went Active in summer keeps that status through
# the following Nov–Feb off-season, then resets at the start of the new
# on-season if it hasn't re-qualified.
#
# `perfs` must cover the full hotel history (not date-filtered) so that
# the prior on-season data is visible during off-season evaluations.

_ON_SEASON_MONTHS = frozenset({3, 4, 5, 6, 7, 8, 9, 10})

# Ordered thresholds (highest first) — Class A ≥30/mo, B ≥15/mo, C ≥3/mo or ≥1 last week
_CLASS_THRESHOLDS = [("A", 30), ("B", 15), ("C", 3)]


def _active_hotel_classes(
    perfs: List,          # ALL WeeklyPerformance rows for the hotel set (unfiltered)
    data_max_week: date,  # latest week present in the data
    valid_hotel_ids: Optional[set] = None,
) -> Dict[int, str]:
    """
    Return {hotel_id: class} for every hotel that qualifies as Active.
    class is "A" (≥30/mo), "B" (≥15/mo), or "C" (≥3/mo or ≥1 last week).
    Hotels that don't qualify are absent from the dict.

    valid_hotel_ids, if given, restricts the result to hotels in that set —
    used to exclude placeholder/non-property entries (e.g. a hotel with no
    room count, such as a generic "Other" bucket from the source data) from
    Active Hotels / Rooms Live, since they aren't real properties.

    Off-season carry-over: when data_max_week is in Jan–Feb the function looks
    at the previous year's on-season (Mar–Oct) so hotels that qualified last
    summer remain active through the winter.
    """
    on_season_year = data_max_week.year - 1 if data_max_week.month <= 2 else data_max_week.year

    # Monthly booking totals per hotel (on-season months of the relevant year only)
    hotel_monthly: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for p in perfs:
        if (p.week_start_date.year == on_season_year and
                p.week_start_date.month in _ON_SEASON_MONTHS):
            hotel_monthly[p.hotel_id][p.week_start_date.month] += p.transactions

    # Peak single-month total per hotel
    hotel_peak: Dict[int, int] = {
        hid: max(months.values(), default=0)
        for hid, months in hotel_monthly.items()
    }

    # Bookings in the past 4 weeks (inclusive) — prevents flicker from a single quiet week
    four_weeks_ago = data_max_week - timedelta(weeks=3)
    hotel_recent: Dict[int, int] = defaultdict(int)
    for p in perfs:
        if p.week_start_date >= four_weeks_ago:
            hotel_recent[p.hotel_id] += p.transactions

    result: Dict[int, str] = {}
    for hid in {p.hotel_id for p in perfs}:
        if valid_hotel_ids is not None and hid not in valid_hotel_ids:
            continue
        peak   = hotel_peak.get(hid, 0)
        recent = hotel_recent[hid]
        if peak >= 30:
            result[hid] = "A"
        elif peak >= 15:
            result[hid] = "B"
        elif peak >= 3 or recent >= 1:
            result[hid] = "C"
    return result


def get_hotel_kpis(
    db: Session,
    hotel: Hotel,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> HotelKPIs:
    q = db.query(WeeklyPerformance).filter(WeeklyPerformance.hotel_id == hotel.id)
    if date_from:
        q = q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:
        q = q.filter(WeeklyPerformance.week_start_date <= date_to)
    perfs = q.all()

    if not perfs:
        return HotelKPIs(
            hotel_id=hotel.id, hotel_name=hotel.name, market=hotel.market,
            property_type=hotel.property_type, room_count=hotel.room_count,
            pipeline_status=hotel.pipeline_status, saas_mrr=hotel.saas_mrr,
            is_alsabini=bool(hotel.is_alsabini),
            total_gmv=0, total_transactions=0, total_bookings=0,
            avg_take_rate=0, net_revenue=0, arpar_bg=0, attach_rate=0,
            aov=0, is_active=False, weeks_of_data=0
        )

    total_gmv          = sum(p.gmv for p in perfs)
    total_transactions = sum(p.transactions for p in perfs)
    total_free         = sum(p.free_transactions or 0 for p in perfs)
    total_bookings     = total_transactions + total_free
    avg_take_rate      = sum(p.take_rate for p in perfs) / len(perfs)
    net_revenue        = sum(
        p.bg_gross_revenue if p.bg_gross_revenue is not None else p.gmv * (p.take_rate / 100)
        for p in perfs
    )
    arpar_bg           = net_revenue / hotel.room_count if hotel.room_count else 0
    attach_rate        = (total_transactions / hotel.room_count * 100) if hotel.room_count else 0
    aov                = total_gmv / total_transactions if total_transactions else 0

    inc_rows  = [p.incremental_revenue for p in perfs if p.incremental_revenue is not None]
    dbu_rows  = [p.direct_booking_uplift for p in perfs if p.direct_booking_uplift is not None]
    og_rows   = [p.offers_generated for p in perfs if p.offers_generated is not None]
    oc_rows   = [p.offers_conversion for p in perfs if p.offers_conversion is not None]
    canc_rows = [p.cancellation_rate for p in perfs if p.cancellation_rate is not None]

    # Active status: use full hotel history (not date-filtered) so off-season
    # carry-over from the prior on-season is correctly reflected.
    # Use the GLOBAL max week across all hotels in the date window so that
    # this hotel's classification uses the same reference date as the portfolio
    # summary (avoids mismatch when this hotel has no recent data).
    all_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id == hotel.id
    ).all()
    global_max_q = db.query(func.max(WeeklyPerformance.week_start_date))
    if date_from: global_max_q = global_max_q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   global_max_q = global_max_q.filter(WeeklyPerformance.week_start_date <= date_to)
    data_max_week  = global_max_q.scalar() or max(p.week_start_date for p in perfs)
    valid_ids      = {hotel.id} if hotel.room_count else set()
    hotel_classes  = _active_hotel_classes(all_perfs, data_max_week, valid_hotel_ids=valid_ids)
    activity_class = hotel_classes.get(hotel.id)
    is_active      = activity_class is not None

    return HotelKPIs(
        hotel_id=hotel.id, hotel_name=hotel.name, market=hotel.market,
        property_type=hotel.property_type, room_count=hotel.room_count,
        pipeline_status=hotel.pipeline_status, saas_mrr=hotel.saas_mrr,
        is_alsabini=bool(hotel.is_alsabini),
        total_gmv=round(total_gmv, 2),
        total_transactions=total_transactions,
        total_bookings=total_bookings,
        avg_take_rate=round(avg_take_rate, 2),
        net_revenue=round(net_revenue, 2),
        arpar_bg=round(arpar_bg, 2),
        attach_rate=round(attach_rate, 2),
        aov=round(aov, 2),
        is_active=is_active,
        activity_class=activity_class,
        weeks_of_data=len(perfs),
        avg_incremental_revenue=round(sum(inc_rows)/len(inc_rows), 2) if inc_rows else None,
        avg_direct_booking_uplift=round(sum(dbu_rows)/len(dbu_rows), 2) if dbu_rows else None,
        total_offers_generated=sum(og_rows) if og_rows else None,
        avg_offers_conversion=round(sum(oc_rows)/len(oc_rows), 2) if oc_rows else None,
        avg_cancellation_rate=round(sum(canc_rows)/len(canc_rows), 1) if canc_rows else None,
    )


def get_hotel_trend(
    db: Session,
    hotel_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[HotelTrend]:
    hotel      = db.query(Hotel).filter(Hotel.id == hotel_id).first()
    room_count = hotel.room_count if hotel else 0

    q = db.query(WeeklyPerformance).filter(WeeklyPerformance.hotel_id == hotel_id)
    if date_from: q = q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   q = q.filter(WeeklyPerformance.week_start_date <= date_to)
    perfs = q.order_by(WeeklyPerformance.week_start_date).all()

    # Build lookup for prior-year data (364 days = 52 weeks, preserves day-of-week)
    prev_lookup: dict = {}
    if perfs:
        py_from = perfs[0].week_start_date  - timedelta(days=364)
        py_to   = perfs[-1].week_start_date - timedelta(days=364)
        prev_perfs = (
            db.query(WeeklyPerformance)
            .filter(
                WeeklyPerformance.hotel_id == hotel_id,
                WeeklyPerformance.week_start_date >= py_from,
                WeeklyPerformance.week_start_date <= py_to,
            )
            .all()
        )
        prev_lookup = {p.week_start_date: p for p in prev_perfs}

    result = []
    for p in perfs:
        prev = prev_lookup.get(p.week_start_date - timedelta(days=364))
        result.append(HotelTrend(
            week_start_date=p.week_start_date,
            gmv=round(p.gmv, 2),
            transactions=p.transactions,
            net_revenue=round(
                p.bg_gross_revenue if p.bg_gross_revenue is not None
                else p.gmv * (p.take_rate / 100), 2
            ),
            take_rate=round(p.take_rate, 2),
            attach_rate=round(p.transactions / room_count * 100, 2) if room_count else 0,
            prev_gmv=round(prev.gmv, 2) if prev else None,
            prev_net_revenue=round(
                prev.bg_gross_revenue if prev and prev.bg_gross_revenue is not None
                else (prev.gmv * (prev.take_rate / 100) if prev else 0), 2
            ) if prev else None,
            prev_transactions=prev.transactions if prev else None,
        ))
    return result


# ── NRR helper ───────────────────────────────────────────────────────────────

def _compute_nrr(
    db: Session,
    hotel_ids: List[int],
    date_from: Optional[date],
    date_to: Optional[date],
) -> Optional[float]:
    """MoM Net Revenue Retention for the retained hotel cohort."""
    if date_from and date_to:
        period_days = max(1, (date_to - date_from).days)
        prev_from   = date_from - timedelta(days=period_days)
        prev_to     = date_from - timedelta(days=1)
        curr_from, curr_to = date_from, date_to
    else:
        today      = date.today()
        curr_from  = today.replace(day=1)
        prev_to    = curr_from - timedelta(days=1)
        prev_from  = prev_to.replace(day=1)
        curr_to    = today

    def _rev(perfs):
        return sum(p.gmv * (p.take_rate / 100) for p in perfs)

    curr_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids),
        WeeklyPerformance.week_start_date >= curr_from,
        WeeklyPerformance.week_start_date <= curr_to,
    ).all()

    prev_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids),
        WeeklyPerformance.week_start_date >= prev_from,
        WeeklyPerformance.week_start_date <= prev_to,
    ).all()

    retained = set(p.hotel_id for p in curr_perfs) & set(p.hotel_id for p in prev_perfs)
    if not retained:
        return None

    curr_rev = _rev([p for p in curr_perfs if p.hotel_id in retained])
    prev_rev = _rev([p for p in prev_perfs if p.hotel_id in retained])
    return round(curr_rev / prev_rev * 100, 1) if prev_rev else None


# ── Portfolio Summary ─────────────────────────────────────────────────────────

def get_portfolio_summary(
    db: Session,
    market: Optional[str] = None,
    property_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> PortfolioSummary:
    # ── Hotel filter ─────────────────────────────────────────────────────────
    query = db.query(Hotel)
    if market:        query = query.filter(Hotel.market == market)
    if property_type: query = query.filter(Hotel.property_type == property_type)
    if status:        query = query.filter(Hotel.pipeline_status == status)
    hotels    = query.all()
    hotel_ids = [h.id for h in hotels]

    if not hotel_ids:
        return PortfolioSummary(
            total_active_hotels=0, total_rooms_live=0, total_gmv_season=0,
            total_net_revenue=0, blended_take_rate=0, saas_mrr=0
        )

    # ── Performance data ─────────────────────────────────────────────────────
    perf_q = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    )
    if date_from: perf_q = perf_q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   perf_q = perf_q.filter(WeeklyPerformance.week_start_date <= date_to)
    season_perfs = perf_q.all()

    # ── Period length (days) ─────────────────────────────────────────────────
    if date_from and date_to:
        days = max(1, (date_to - date_from).days)
    elif season_perfs:
        min_d = min(p.week_start_date for p in season_perfs)
        max_d = max(p.week_start_date for p in season_perfs)
        days  = max(1, (max_d - min_d).days + 7)
    else:
        days = 365
    months = max(1.0, days / 30.0)

    # ── Core aggregates ───────────────────────────────────────────────────────
    total_gmv      = sum(p.gmv for p in season_perfs)
    total_revenue  = sum(
        p.bg_gross_revenue if p.bg_gross_revenue is not None
        else p.gmv * (p.take_rate / 100)
        for p in season_perfs
    )
    blended_take   = (total_revenue / total_gmv * 100) if total_gmv else 0
    total_txns     = sum(p.transactions for p in season_perfs)
    total_free     = sum(p.free_transactions or 0 for p in season_perfs)
    total_bookings = total_txns + total_free
    # Active hotel check uses the full unfiltered history so that off-season
    # carry-over from the prior on-season is visible even when a date filter
    # is applied.
    data_max_week = max((p.week_start_date for p in season_perfs), default=date.today())
    all_hotel_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    ).all()
    valid_hotel_ids  = {h.id for h in hotels if h.room_count}
    hotel_classes    = _active_hotel_classes(all_hotel_perfs, data_max_week, valid_hotel_ids=valid_hotel_ids)
    active_hotel_ids = set(hotel_classes.keys())
    active_count     = len(active_hotel_ids)
    class_a_hotels   = sum(1 for c in hotel_classes.values() if c == "A")
    class_b_hotels   = sum(1 for c in hotel_classes.values() if c == "B")
    class_c_hotels   = sum(1 for c in hotel_classes.values() if c == "C")

    # Rooms: scope to booking-active hotels only.
    total_rooms = sum(h.room_count for h in hotels if h.id in active_hotel_ids)

    # Rooms broken down by class
    hotel_room_map = {h.id: h.room_count for h in hotels}
    rooms_class_a  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes.items() if cls == "A")
    rooms_class_b  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes.items() if cls == "B")
    rooms_class_c  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes.items() if cls == "C")

    # MNR = Active Hotels (A+B+C) × Avg Monthly Net Revenue per Active Hotel
    # Revenue is scoped to active hotels only; avg divides by active_count
    active_revenue = sum(
        p.bg_gross_revenue if p.bg_gross_revenue is not None else p.gmv * (p.take_rate / 100)
        for p in season_perfs
        if p.hotel_id in active_hotel_ids
    )
    avg_monthly_net_rev_per_hotel = (active_revenue / months / active_count) if (months > 0 and active_count > 0) else 0.0
    saas_mrr = round(active_count * avg_monthly_net_rev_per_hotel, 2)

    # ── Tier 1 · Hotel Value ─────────────────────────────────────────────────

    # ARPAR_BG (#1) — rooms-weighted: total net revenue ÷ total rooms
    # Uses bg_gross_revenue directly (consistent with portfolio net revenue).
    # Hotels with room_count = 0 are excluded (no meaningful ARPAR possible).
    _arpar_net_rev = 0.0
    _arpar_rooms   = 0
    for h in hotels:
        h_perfs = [p for p in season_perfs if p.hotel_id == h.id]
        if h_perfs and h.room_count:
            _arpar_net_rev += sum(
                p.bg_gross_revenue if p.bg_gross_revenue is not None
                else p.gmv * (p.take_rate / 100)
                for p in h_perfs
            )
            _arpar_rooms += h.room_count
    avg_arpar_bg = round(_arpar_net_rev / _arpar_rooms, 2) if _arpar_rooms else None

    # Attach Rate (#3)
    portfolio_attach_rate = round(total_txns / total_rooms * 100, 2) if total_rooms else None

    # Attach Rate by class — cumulative (B includes A, C includes A+B)
    a_ids  = {hid for hid, cls in hotel_classes.items() if cls == "A"}
    ab_ids = {hid for hid, cls in hotel_classes.items() if cls in ("A", "B")}

    def _attach_for_class(hotel_id_set):
        t = sum(p.transactions for p in season_perfs if p.hotel_id in hotel_id_set)
        r = sum(hotel_room_map.get(hid, 0) for hid in hotel_id_set)
        return round(t / r * 100, 2) if r else None

    attach_rate_class_a = _attach_for_class(a_ids)
    attach_rate_class_b = _attach_for_class(ab_ids)
    attach_rate_class_c = portfolio_attach_rate  # all active = C+B+A

    # MNR by class — cumulative, same pattern as attach rate
    # MNR = revenue from class hotels / months (class C = saas_mrr)
    def _mnr_for_class(hotel_id_set):
        rev = sum(
            p.bg_gross_revenue if p.bg_gross_revenue is not None else p.gmv * (p.take_rate / 100)
            for p in season_perfs if p.hotel_id in hotel_id_set
        )
        return round(rev / months, 2) if months > 0 else None

    saas_mrr_class_a = _mnr_for_class(a_ids)
    saas_mrr_class_b = _mnr_for_class(ab_ids)

    # ARPAR_BG split by Alsabini / non-Alsabini — same rooms-weighted approach
    def _arpar_for(hotel_subset):
        net_rev = 0.0
        rooms   = 0
        for h in hotel_subset:
            h_perfs = [p for p in season_perfs if p.hotel_id == h.id]
            if h_perfs and h.room_count:
                net_rev += sum(
                    p.bg_gross_revenue if p.bg_gross_revenue is not None
                    else p.gmv * (p.take_rate / 100)
                    for p in h_perfs
                )
                rooms += h.room_count
        return round(net_rev / rooms, 2) if rooms else None

    alsabini_hotels     = [h for h in hotels if h.is_alsabini]
    non_alsabini_hotels = [h for h in hotels if not h.is_alsabini]
    arpar_bg_alsabini     = _arpar_for(alsabini_hotels)
    arpar_bg_non_alsabini = _arpar_for(non_alsabini_hotels)

    # Incremental Revenue (#2)
    inc_vals = [p.incremental_revenue for p in season_perfs if p.incremental_revenue is not None]
    avg_incremental_revenue = round(sum(inc_vals) / len(inc_vals), 2) if inc_vals else None

    # Incremental Revenue split by Alsabini / non-Alsabini
    alsabini_ids     = {h.id for h in alsabini_hotels}
    non_alsabini_ids = {h.id for h in non_alsabini_hotels}
    def _inc_for(hotel_ids):
        vals = [p.incremental_revenue for p in season_perfs
                if p.hotel_id in hotel_ids and p.incremental_revenue is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    incremental_revenue_alsabini     = _inc_for(alsabini_ids)
    incremental_revenue_non_alsabini = _inc_for(non_alsabini_ids)

    # Direct Booking Uplift (#5)
    dbu_vals = [p.direct_booking_uplift for p in season_perfs if p.direct_booking_uplift is not None]
    avg_direct_booking_uplift = round(sum(dbu_vals) / len(dbu_vals), 2) if dbu_vals else None

    # Cancellation Reduction (#4) — pp below industry; raw avg rate as companion metric
    canc_vals = [p.cancellation_rate for p in season_perfs if p.cancellation_rate is not None]
    avg_cancellation_reduction  = None
    avg_hotel_cancellation_rate = None
    if canc_vals:
        avg_hotel_canc = sum(canc_vals) / len(canc_vals)
        avg_hotel_cancellation_rate = round(avg_hotel_canc, 1)
        avg_cancellation_reduction  = round(
            (INDUSTRY_CANCELLATION_RATE - avg_hotel_canc) / INDUSTRY_CANCELLATION_RATE * 100, 1
        )

    # ── Tier 2 · Engine — Monetisation ───────────────────────────────────────

    avg_aov           = round(total_gmv / total_txns, 2) if total_txns else None
    revenue_per_booking = round(total_revenue / total_bookings, 2) if total_bookings else None

    # Orders per Guest (#11) & ARPG (#12)
    guest_vals = [p.unique_guests for p in season_perfs if p.unique_guests is not None]
    if guest_vals:
        total_guests    = sum(guest_vals)
        orders_per_guest = round(total_bookings / total_guests, 2) if total_guests else None
        avg_arpg        = round(total_revenue / total_guests, 2) if total_guests else None
    else:
        orders_per_guest = avg_arpg = None

    # Category Mix % (#14)
    cat_cars  = sum(p.cars_gmv or 0 for p in season_perfs)
    cat_trans = sum(p.transfers_gmv or 0 for p in season_perfs)
    cat_exp   = sum(p.experiences_gmv or 0 for p in season_perfs)
    cat_well  = sum(p.wellness_gmv or 0 for p in season_perfs)
    cat_other = sum(p.other_gmv or 0 for p in season_perfs)
    cat_total = cat_cars + cat_trans + cat_exp + cat_well + cat_other
    if cat_total > 0:
        category_mix_cars         = round(cat_cars  / cat_total * 100, 1)
        category_mix_transfers    = round(cat_trans / cat_total * 100, 1)
        category_mix_experiences  = round(cat_exp   / cat_total * 100, 1)
        category_mix_wellness     = round(cat_well  / cat_total * 100, 1)
        category_mix_other        = round(cat_other / cat_total * 100, 1)
    else:
        category_mix_cars = category_mix_transfers = category_mix_experiences = \
            category_mix_wellness = category_mix_other = None

    # Revenue Segment — BG General (col I) vs Alsabini (col K)
    _has_segment = any(p.bg_general_gmv is not None or p.alsabini_gmv is not None for p in season_perfs)
    if _has_segment:
        bg_general_gmv      = round(sum(p.bg_general_gmv   or 0 for p in season_perfs), 2)
        bg_general_revenue  = round(sum(p.bg_general_revenue or 0 for p in season_perfs), 2)
        alsabini_gmv        = round(sum(p.alsabini_gmv     or 0 for p in season_perfs), 2)
        alsabini_revenue    = round(sum(p.alsabini_revenue  or 0 for p in season_perfs), 2)
        seg_rev_total  = bg_general_revenue + alsabini_revenue
        bg_general_pct = round(bg_general_revenue / seg_rev_total * 100, 1) if seg_rev_total else None
        alsabini_pct   = round(alsabini_revenue   / seg_rev_total * 100, 1) if seg_rev_total else None
    else:
        bg_general_gmv = bg_general_revenue = alsabini_gmv = alsabini_revenue = None
        bg_general_pct = alsabini_pct = None

    # Vertical Breakdown — raw col-C values with GMV + Revenue
    vert_totals: Dict[str, Dict[str, float]] = defaultdict(lambda: {"gmv": 0.0, "revenue": 0.0})
    _has_vert = False
    for p in season_perfs:
        if p.vertical_breakdown:
            _has_vert = True
            try:
                for v, vals in json.loads(p.vertical_breakdown).items():
                    vert_totals[v]["gmv"]     += vals.get("gmv", 0.0)
                    vert_totals[v]["revenue"] += vals.get("revenue", 0.0)
            except (json.JSONDecodeError, AttributeError):
                pass
    if _has_vert:
        total_vert_gmv = sum(v["gmv"]     for v in vert_totals.values())
        total_vert_rev = sum(v["revenue"] for v in vert_totals.values())
        vertical_breakdown = {
            k: {
                "gmv":         round(v["gmv"],     2),
                "revenue":     round(v["revenue"], 2),
                "gmv_pct":     round(v["gmv"]     / total_vert_gmv * 100, 1) if total_vert_gmv else 0.0,
                "revenue_pct": round(v["revenue"] / total_vert_rev * 100, 1) if total_vert_rev else 0.0,
            }
            for k, v in sorted(vert_totals.items(), key=lambda x: -x[1]["gmv"])
            if v["gmv"] > 0
        }
    else:
        vertical_breakdown = None

    # Purchase Channel — Direct (Catalog) vs Concierge (Offer)
    _has_channel = any(p.direct_gmv is not None or p.concierge_gmv is not None for p in season_perfs)
    if _has_channel:
        direct_gmv     = round(sum(p.direct_gmv     or 0 for p in season_perfs), 2)
        direct_revenue = round(sum(p.direct_revenue  or 0 for p in season_perfs), 2)
        concierge_gmv     = round(sum(p.concierge_gmv     or 0 for p in season_perfs), 2)
        concierge_revenue = round(sum(p.concierge_revenue  or 0 for p in season_perfs), 2)
        channel_total = direct_gmv + concierge_gmv
        direct_pct    = round(direct_gmv    / channel_total * 100, 1) if channel_total else None
        concierge_pct = round(concierge_gmv / channel_total * 100, 1) if channel_total else None
    else:
        direct_gmv = direct_revenue = concierge_gmv = concierge_revenue = None
        direct_pct = concierge_pct = None

    # ── Tier 2 · Engine — Funnel ─────────────────────────────────────────────

    # Pre-Arrival (#15) and Post-Booking (#16) Attach Rates
    pre_arr  = [p.pre_arrival_bookings for p in season_perfs if p.pre_arrival_bookings is not None]
    post_bk  = [p.post_booking_bookings for p in season_perfs if p.post_booking_bookings is not None]
    pre_arrival_attach_rate   = round(sum(pre_arr) / total_rooms * 100, 2) if pre_arr and total_rooms else None
    post_booking_attach_rate  = round(sum(post_bk) / total_rooms * 100, 2) if post_bk and total_rooms else None

    # Offers
    og_vals = [p.offers_generated for p in season_perfs if p.offers_generated is not None]
    oc_vals = [p.offers_conversion for p in season_perfs if p.offers_conversion is not None]
    total_offers_generated = sum(og_vals) if og_vals else None
    avg_offers_conversion  = round(sum(oc_vals) / len(oc_vals), 2) if oc_vals else None

    # WhatsApp Conversion Uplift (#18)
    wa_pairs = [(p.whatsapp_bookings, p.email_bookings)
                for p in season_perfs
                if p.whatsapp_bookings is not None and p.email_bookings is not None]
    if wa_pairs and total_rooms:
        wa_total = sum(r[0] for r in wa_pairs)
        em_total = sum(r[1] for r in wa_pairs)
        wa_attach = wa_total / total_rooms * 100
        em_attach = em_total / total_rooms * 100
        whatsapp_conversion_uplift = round((wa_attach / em_attach - 1) * 100, 1) if em_attach else None
    else:
        whatsapp_conversion_uplift = None

    # Orders per Day (#19)
    orders_per_day = round(total_bookings / days, 2) if total_bookings else None

    # ── Tier 3 · Repeatability ───────────────────────────────────────────────

    hotel_attach_rates: List[float] = []
    hotel_arpars2:      List[float] = []
    for h in hotels:
        h_perfs = [p for p in season_perfs if p.hotel_id == h.id]
        if h_perfs and h.room_count:
            h_txns = sum(p.transactions for p in h_perfs)
            hotel_attach_rates.append(h_txns / h.room_count * 100)
            h_gmv  = sum(p.gmv for p in h_perfs)
            h_rate = sum(p.take_rate for p in h_perfs) / len(h_perfs)
            hotel_arpars2.append((h_gmv * h_rate / 100) / h.room_count)

    attach_rate_variance = round(statistics.stdev(hotel_attach_rates), 2) if len(hotel_attach_rates) >= 2 else None
    arpar_variance       = round(statistics.stdev(hotel_arpars2), 2)       if len(hotel_arpars2) >= 2 else None

    # % Catalogue Active (#25)
    cat_total_vals  = [p.catalogue_total  for p in season_perfs if p.catalogue_total  is not None]
    cat_active_vals = [p.catalogue_active for p in season_perfs if p.catalogue_active is not None]
    ct = sum(cat_total_vals)
    ca = sum(cat_active_vals)
    pct_catalogue_active = round(ca / ct * 100, 1) if ct > 0 and cat_active_vals else None

    # Fill Rate (#26)
    attempt_vals = [p.booking_attempts for p in season_perfs if p.booking_attempts is not None]
    total_attempts = sum(attempt_vals) if attempt_vals else 0
    fill_rate = round(total_txns / total_attempts * 100, 1) if total_attempts else None

    # Transactions per Room per Day (#27)
    transactions_per_room_per_day = round(total_txns / total_rooms / days, 4) if total_rooms and total_txns else None

    # ── Tier 4 · Scale ───────────────────────────────────────────────────────

    # New Active Hotels (#30) — hotels that are Active this period but were not
    # Active in all data prior to this period (using the same activation rule).
    new_active_hotels = 0
    for h in hotels:
        if h.id not in active_hotel_ids:
            continue  # not active now → can't be "newly" active
        all_perfs  = db.query(WeeklyPerformance).filter(WeeklyPerformance.hotel_id == h.id).all()
        season_ids = {p.id for p in season_perfs if p.hotel_id == h.id}
        prev_perfs = [p for p in all_perfs if p.id not in season_ids]
        if not prev_perfs:
            new_active_hotels += 1  # no history at all → definitely new
            continue
        prev_max_week = max(p.week_start_date for p in prev_perfs)
        was_active    = h.id in _active_hotel_classes(prev_perfs, prev_max_week)
        if not was_active:
            new_active_hotels += 1

    # Revenue per Hotel per Month (#31)
    revenue_per_hotel_per_month = round(total_revenue / active_count / months, 2) if active_count else None

    # Expansion Revenue (#33) & Rate (#34)
    exp_hotel_ids  = [h.id for h in hotels if h.is_chain_expansion]
    expansion_revenue = round(
        sum(p.gmv * (p.take_rate / 100) for p in season_perfs if p.hotel_id in exp_hotel_ids), 2
    ) if exp_hotel_ids else None
    expansion_rate = round(len(exp_hotel_ids) / len(hotels) * 100, 1) if hotels else None

    # Onboarded → Active Conversion (#36)
    total_hotels_count = db.query(Hotel).count()
    onboarded_to_active_rate = round(active_count / total_hotels_count * 100, 1) if total_hotels_count else None

    # NRR (#37)
    nrr = _compute_nrr(db, hotel_ids, date_from, date_to)

    # Hotels in Pipeline (#49)
    hotels_in_pipeline = sum(1 for h in db.query(Hotel).all() if h.pipeline_status == "Pipeline")

    # ── Tier 5 · Efficiency ───────────────────────────────────────────────────

    # Time to Activate (#46) — from Hotel model fields
    act_hotels = [h for h in hotels if h.date_signed and h.date_activated]
    avg_time_to_activate = round(
        sum((h.date_activated - h.date_signed).days for h in act_hotels) / len(act_hotels), 0
    ) if act_hotels else None

    # LTV, LTV:CAC, CAC Payback (#40-43)
    cac_hotels = [h for h in hotels if h.cac is not None]
    avg_cac = round(sum(h.cac for h in cac_hotels) / len(cac_hotels), 2) if cac_hotels else None

    # Hotel LTV = avg revenue/hotel/month × avg hotel lifetime in months
    hotel_lifetimes = []
    for h in hotels:
        h_weeks = len(set(p.week_start_date for p in season_perfs if p.hotel_id == h.id))
        if h_weeks:
            hotel_lifetimes.append(h_weeks / 4.33)
    avg_lifetime_months = sum(hotel_lifetimes) / len(hotel_lifetimes) if hotel_lifetimes else None
    hotel_ltv = round(revenue_per_hotel_per_month * avg_lifetime_months, 2) \
        if revenue_per_hotel_per_month and avg_lifetime_months else None
    ltv_cac_ratio   = round(hotel_ltv / avg_cac, 2) if hotel_ltv and avg_cac else None
    cac_payback_months = round(avg_cac / revenue_per_hotel_per_month, 1) \
        if avg_cac and revenue_per_hotel_per_month else None

    # MNR Growth Rate = (This Month MNR − Last Month MNR) ÷ Last Month MNR × 100
    # Consistent with MNR formula: uses bg_gross_revenue (not gmv×take_rate),
    # and only includes revenue from active hotels (active_hotel_ids).
    monthly_rev: Dict[tuple, float] = defaultdict(float)
    for p in season_perfs:
        if p.hotel_id not in active_hotel_ids:
            continue
        mk = (p.week_start_date.year, p.week_start_date.month)
        monthly_rev[mk] += (
            p.bg_gross_revenue if p.bg_gross_revenue is not None
            else p.gmv * (p.take_rate / 100)
        )
    sorted_months = sorted(monthly_rev.keys())
    mrr_growth = None
    if len(sorted_months) >= 2:
        this_mnr = monthly_rev[sorted_months[-1]]
        prev_mnr = monthly_rev[sorted_months[-2]]
        if prev_mnr:
            mrr_growth = round((this_mnr - prev_mnr) / prev_mnr * 100, 2)

    # Financial snapshot — still used for cash / burn / gross margin / headcount
    snapshots = db.query(FinancialSnapshot).order_by(
        FinancialSnapshot.snapshot_date.desc()
    ).limit(1).all()
    snapshot = snapshots[0] if snapshots else None

    # Gross Margin % (#47) and Revenue per Employee (#48)
    gross_margin_pct    = None
    revenue_per_employee = None
    if snapshot:
        if snapshot.cogs is not None and total_revenue > 0:
            gross_margin_pct = round((total_revenue - snapshot.cogs) / total_revenue * 100, 1)
        if snapshot.headcount and total_revenue > 0:
            annual_rev = total_revenue * (365 / days)
            revenue_per_employee = round(annual_rev / snapshot.headcount, 0)

    return PortfolioSummary(
        # Tier 1
        total_active_hotels=active_count,
        class_a_hotels=class_a_hotels,
        class_b_hotels=class_b_hotels,
        class_c_hotels=class_c_hotels,
        total_rooms_live=total_rooms,
        rooms_class_a=rooms_class_a,
        rooms_class_b=rooms_class_b,
        rooms_class_c=rooms_class_c,
        total_gmv_season=round(total_gmv, 2),
        total_net_revenue=round(total_revenue, 2),
        blended_take_rate=round(blended_take, 2),
        avg_arpar_bg=avg_arpar_bg,
        arpar_bg_alsabini=arpar_bg_alsabini,
        arpar_bg_non_alsabini=arpar_bg_non_alsabini,
        portfolio_attach_rate=portfolio_attach_rate,
        attach_rate_class_a=attach_rate_class_a,
        attach_rate_class_b=attach_rate_class_b,
        attach_rate_class_c=attach_rate_class_c,
        avg_direct_booking_uplift=avg_direct_booking_uplift,
        avg_incremental_revenue=avg_incremental_revenue,
        incremental_revenue_alsabini=incremental_revenue_alsabini,
        incremental_revenue_non_alsabini=incremental_revenue_non_alsabini,
        avg_cancellation_reduction=avg_cancellation_reduction,
        avg_hotel_cancellation_rate=avg_hotel_cancellation_rate,
        # Tier 2 – Core Revenue
        saas_mrr=round(saas_mrr, 2),
        saas_mrr_class_a=saas_mrr_class_a,
        saas_mrr_class_b=saas_mrr_class_b,
        mrr_growth_rate=mrr_growth,
        # Tier 2 – Monetisation
        avg_aov=avg_aov,
        orders_per_guest=orders_per_guest,
        avg_arpg=avg_arpg,
        revenue_per_booking=revenue_per_booking,
        category_mix_cars=category_mix_cars,
        category_mix_transfers=category_mix_transfers,
        category_mix_experiences=category_mix_experiences,
        category_mix_wellness=category_mix_wellness,
        category_mix_other=category_mix_other,
        direct_gmv=direct_gmv,
        direct_revenue=direct_revenue,
        concierge_gmv=concierge_gmv,
        concierge_revenue=concierge_revenue,
        direct_pct=direct_pct,
        concierge_pct=concierge_pct,
        bg_general_gmv=bg_general_gmv,
        bg_general_revenue=bg_general_revenue,
        alsabini_gmv=alsabini_gmv,
        alsabini_revenue=alsabini_revenue,
        bg_general_pct=bg_general_pct,
        alsabini_pct=alsabini_pct,
        vertical_breakdown=vertical_breakdown,
        # Tier 2 – Funnel
        pre_arrival_attach_rate=pre_arrival_attach_rate,
        post_booking_attach_rate=post_booking_attach_rate,
        total_paid_transactions=total_txns,
        total_bookings=total_bookings,
        total_offers_generated=total_offers_generated,
        avg_offers_conversion=avg_offers_conversion,
        whatsapp_conversion_uplift=whatsapp_conversion_uplift,
        orders_per_day=orders_per_day,
        # Tier 3
        attach_rate_variance=attach_rate_variance,
        arpar_variance=arpar_variance,
        pct_catalogue_active=pct_catalogue_active,
        fill_rate=fill_rate,
        transactions_per_room_per_day=transactions_per_room_per_day,
        # Tier 4
        new_active_hotels=new_active_hotels,
        revenue_per_hotel_per_month=revenue_per_hotel_per_month,
        expansion_revenue=expansion_revenue,
        expansion_rate=expansion_rate,
        onboarded_to_active_rate=onboarded_to_active_rate,
        nrr=nrr,
        hotels_in_pipeline=hotels_in_pipeline,
        # Tier 5
        ltv_cac_ratio=ltv_cac_ratio,
        cac_payback_months=cac_payback_months,
        avg_cac=avg_cac,
        hotel_ltv=hotel_ltv,
        avg_time_to_activate=avg_time_to_activate,
        gross_margin_pct=gross_margin_pct,
        revenue_per_employee=revenue_per_employee,
        # Financial
        cash_balance=snapshot.cash_balance if snapshot else None,
        runway_months=snapshot.runway_months if snapshot else None,
        monthly_burn_rate=snapshot.monthly_burn_rate if snapshot else None,
    )


# ── Portfolio Trend ──────────────────────────────────────────────────────────

def get_portfolio_trend(
    db: Session,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    market: Optional[str] = None,
    property_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[PortfolioTrendPoint]:
    query = db.query(Hotel)
    if market:        query = query.filter(Hotel.market == market)
    if property_type: query = query.filter(Hotel.property_type == property_type)
    if status:        query = query.filter(Hotel.pipeline_status == status)

    hotels         = query.all()
    hotel_ids      = [h.id for h in hotels]
    total_rooms    = sum(h.room_count for h in hotels if h.room_count)
    hotel_room_map = {h.id: (h.room_count or 0) for h in hotels}
    valid_hotel_ids = {hid for hid, rooms in hotel_room_map.items() if rooms}

    if not hotel_ids:
        return []

    # Date-filtered perfs for the metrics (GMV, revenue, transactions)
    perf_q = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    )
    if date_from: perf_q = perf_q.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   perf_q = perf_q.filter(WeeklyPerformance.week_start_date <= date_to)
    perfs = perf_q.order_by(WeeklyPerformance.week_start_date).all()

    # ALL historical perfs (unfiltered) — needed so that off-season carry-over
    # is correctly accounted for when computing active_hotels per week, and so
    # prior-year net revenue can be looked up even when it falls outside the
    # selected date range.
    all_hist_perfs = db.query(WeeklyPerformance).filter(
        WeeklyPerformance.hotel_id.in_(hotel_ids)
    ).order_by(WeeklyPerformance.week_start_date).all()

    # Full-history net revenue per week (portfolio-wide, unfiltered by date
    # range) — used to look up "same week last season" (364 days back,
    # preserves day-of-week alignment) for the Net Revenue drill-down.
    hist_net_rev_by_week: Dict[date, float] = defaultdict(float)
    for p in all_hist_perfs:
        hist_net_rev_by_week[p.week_start_date] += (
            p.bg_gross_revenue if p.bg_gross_revenue is not None
            else p.gmv * (p.take_rate / 100)
        )

    weekly: Dict[str, dict] = defaultdict(lambda: {
        "gmv": 0.0, "net_revenue": 0.0, "transactions": 0, "hotel_ids": set(),
        "alsabini_revenue": 0.0, "has_alsabini": False,
        "cancellations": 0, "has_cancellations": False,
    })
    # Per-hotel per-week transactions — used to compute per-class attach rates
    week_hotel_txns: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for p in perfs:
        key = str(p.week_start_date)
        weekly[key]["gmv"]          += p.gmv
        weekly[key]["net_revenue"]  += (
            p.bg_gross_revenue if p.bg_gross_revenue is not None
            else p.gmv * (p.take_rate / 100)
        )
        weekly[key]["transactions"] += p.transactions
        weekly[key]["hotel_ids"].add(p.hotel_id)
        week_hotel_txns[key][p.hotel_id] += p.transactions
        if p.alsabini_revenue is not None:
            weekly[key]["alsabini_revenue"] += p.alsabini_revenue
            weekly[key]["has_alsabini"] = True
        if p.cancelled_transactions is not None:
            weekly[key]["cancellations"] += p.cancelled_transactions
            weekly[key]["has_cancellations"] = True

    # Build the carry-over active-hotel count per week using the same
    # classification logic as the portfolio summary.  We accumulate ALL
    # historical perfs up to (and including) each week so that on-season peaks
    # and the 4-week recency window are evaluated with full context.
    sorted_weeks  = sorted(weekly.keys())
    hist_idx      = 0
    hist_accum: List = []

    result = []
    for week_str in sorted_weeks:
        week_date = date.fromisoformat(week_str)

        # Advance the accumulated history up to this week (inclusive)
        while hist_idx < len(all_hist_perfs) and all_hist_perfs[hist_idx].week_start_date <= week_date:
            hist_accum.append(all_hist_perfs[hist_idx])
            hist_idx += 1

        # Classify hotels using full accumulated history and this week as reference
        hotel_classes_week = _active_hotel_classes(hist_accum, week_date, valid_hotel_ids=valid_hotel_ids)
        active_count_week  = len(hotel_classes_week)

        # Per-class counts and rooms (non-cumulative, for stacked charts)
        a_count_w  = sum(1 for cls in hotel_classes_week.values() if cls == "A")
        b_count_w  = sum(1 for cls in hotel_classes_week.values() if cls == "B")
        c_count_w  = sum(1 for cls in hotel_classes_week.values() if cls == "C")
        rooms_a_w  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes_week.items() if cls == "A")
        rooms_b_w  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes_week.items() if cls == "B")
        rooms_c_w  = sum(hotel_room_map.get(hid, 0) for hid, cls in hotel_classes_week.items() if cls == "C")
        week_rooms = rooms_a_w + rooms_b_w + rooms_c_w

        # Per-class transactions for this week (active hotels only)
        hotel_txns_w = week_hotel_txns[week_str]
        txns_a_w  = sum(hotel_txns_w.get(hid, 0) for hid, cls in hotel_classes_week.items() if cls == "A")
        txns_ab_w = sum(hotel_txns_w.get(hid, 0) for hid, cls in hotel_classes_week.items() if cls in ("A", "B"))

        rooms_ab_w = rooms_a_w + rooms_b_w
        attach_rate_a_w  = round(txns_a_w  / rooms_a_w  * 100, 2) if rooms_a_w  else 0.0
        attach_rate_ab_w = round(txns_ab_w / rooms_ab_w * 100, 2) if rooms_ab_w else 0.0

        w    = weekly[week_str]
        txns = w["transactions"]
        gmv  = w["gmv"]

        prev_wk = week_date - timedelta(days=364)   # same week last season
        prev_net_revenue = round(hist_net_rev_by_week[prev_wk], 2) if prev_wk in hist_net_rev_by_week else None
        alsabini_revenue = round(w["alsabini_revenue"], 2) if w["has_alsabini"] else None

        cancellations = w["cancellations"] if w["has_cancellations"] else None
        cancellation_rate = None
        if cancellations is not None:
            canc_total = txns + cancellations
            cancellation_rate = round(cancellations / canc_total * 100, 2) if canc_total else 0.0

        result.append(PortfolioTrendPoint(
            week_start_date=week_str,
            gmv=round(gmv, 2),
            net_revenue=round(w["net_revenue"], 2),
            prev_net_revenue=prev_net_revenue,
            alsabini_revenue=alsabini_revenue,
            cancellations=cancellations,
            cancellation_rate=cancellation_rate,
            transactions=txns,
            aov=round(gmv / txns, 2) if txns else 0.0,
            attach_rate=round(txns / week_rooms * 100, 2) if week_rooms else 0.0,
            active_hotels=active_count_week,
            active_hotels_class_a=a_count_w,
            active_hotels_class_b=b_count_w,
            active_hotels_class_c=c_count_w,
            rooms_live=week_rooms,
            rooms_class_a=rooms_a_w,
            rooms_class_b=rooms_b_w,
            rooms_class_c=rooms_c_w,
            txns_class_a=txns_a_w,
            txns_class_ab=txns_ab_w,
            attach_rate_class_a=attach_rate_a_w,
            attach_rate_class_ab=attach_rate_ab_w,
        ))
    return result
