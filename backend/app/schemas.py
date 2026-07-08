from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


class HotelBase(BaseModel):
    name: str
    market: str
    property_type: str
    room_count: int
    seasonality: Optional[str] = None
    pipeline_status: str = "Active"
    saas_mrr: float = 0.0
    hubspot_id: Optional[str] = None


class HotelCreate(HotelBase):
    pass


class HotelOut(HotelBase):
    id: int
    is_alsabini: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WeeklyPerformanceBase(BaseModel):
    hotel_id: int
    week_start_date: date
    gmv: float = 0.0
    transactions: int = 0
    free_transactions: int = 0
    avg_cart_value: float = 0.0
    take_rate: float = 0.0
    bg_gross_revenue: float = 0.0
    total_hotel_checkins: int = 0
    incremental_revenue: Optional[float] = None
    direct_booking_uplift: Optional[float] = None
    offers_generated: Optional[int] = None
    offers_conversion: Optional[float] = None
    direct_gmv: Optional[float] = None
    direct_revenue: Optional[float] = None
    concierge_gmv: Optional[float] = None
    concierge_revenue: Optional[float] = None
    bg_general_gmv: Optional[float] = None
    bg_general_revenue: Optional[float] = None
    alsabini_gmv: Optional[float] = None
    alsabini_revenue: Optional[float] = None


class WeeklyPerformanceCreate(WeeklyPerformanceBase):
    pass


class WeeklyPerformanceOut(WeeklyPerformanceBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FinancialSnapshotBase(BaseModel):
    snapshot_date: date
    cash_balance: float = 0.0
    monthly_burn_rate: float = 0.0
    runway_months: float = 0.0
    total_saas_mrr: float = 0.0
    source: str = "manual"


class FinancialSnapshotCreate(FinancialSnapshotBase):
    pass


class FinancialSnapshotOut(FinancialSnapshotBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── KPI aggregates ──────────────────────────────────────────────────────────

class HotelKPIs(BaseModel):
    hotel_id: int
    hotel_name: str
    market: str
    property_type: str
    room_count: int
    pipeline_status: str
    saas_mrr: float
    total_gmv: float
    total_transactions: int          # Paid bookings (row 42)
    total_bookings: int              # Paid + free bookings (row 43)
    avg_take_rate: float
    net_revenue: float               # BG Net Revenue / Hotel Net Revenue (rows 9, 10)
    arpar_bg: float                  # ARPAR_BG (row 4)
    attach_rate: float               # Attach Rate (row 6)
    aov: float                       # AOV (row 17)
    is_active: bool
    activity_class: Optional[str] = None   # "A" | "B" | "C" | None
    is_alsabini: bool = False
    weeks_of_data: int
    avg_incremental_revenue: Optional[float] = None   # Row 5
    avg_direct_booking_uplift: Optional[float] = None # Row 8
    total_offers_generated: Optional[int] = None      # Row 26
    avg_offers_conversion: Optional[float] = None     # Row 27
    avg_cancellation_rate: Optional[float] = None     # Raw avg weekly cancellation rate


class PortfolioSummary(BaseModel):
    # ── Tier 1 · Hotel Value ─────────────────────────────────────────────────
    total_active_hotels: int                                  # #9 Active Hotels (A+B+C)
    class_a_hotels: Optional[int] = None                      # ≥30 bookings/month
    class_b_hotels: Optional[int] = None                      # ≥15 bookings/month
    class_c_hotels: Optional[int] = None                      # ≥3 bookings/month or ≥1 last week
    total_rooms_live: int                                     # #32 Total Rooms Under Mgmt
    rooms_class_a: Optional[int] = None                       # Rooms in Class A hotels
    rooms_class_b: Optional[int] = None                       # Rooms in Class B hotels
    rooms_class_c: Optional[int] = None                       # Rooms in Class C hotels
    total_gmv_season: float                                   # #50 Guest GMV / GMV
    total_net_revenue: float                                  # #6 BG Net Revenue
    blended_take_rate: float
    avg_arpar_bg: Optional[float] = None                     # #1 ARPAR_BG
    arpar_bg_alsabini: Optional[float] = None                # #1 ARPAR_BG — Alsabini hotels only
    arpar_bg_non_alsabini: Optional[float] = None            # #1 ARPAR_BG — non-Alsabini hotels only
    portfolio_attach_rate: Optional[float] = None            # #3 Attach Rate
    avg_direct_booking_uplift: Optional[float] = None        # #5 Direct Booking Uplift
    avg_incremental_revenue: Optional[float] = None          # #2 Incremental Rev/Hotel
    incremental_revenue_alsabini: Optional[float] = None     # #2 Incremental Rev — Alsabini only
    incremental_revenue_non_alsabini: Optional[float] = None # #2 Incremental Rev — non-Alsabini only
    avg_cancellation_reduction: Optional[float] = None        # #4 Cancellation Reduction (pp below industry)
    avg_hotel_cancellation_rate: Optional[float] = None      # #4b Raw avg hotel cancellation rate
    attach_rate_class_a: Optional[float] = None              # Attach rate — Class A hotels only
    attach_rate_class_b: Optional[float] = None              # Attach rate — Class A+B hotels (cumulative)
    attach_rate_class_c: Optional[float] = None              # Attach rate — all active A+B+C hotels
    # ── Tier 2 · Engine — Core Revenue ──────────────────────────────────────
    saas_mrr: float                                           # #7 MRR (all active, A+B+C)
    saas_mrr_class_a: Optional[float] = None                 # MNR — Class A hotels only
    saas_mrr_class_b: Optional[float] = None                 # MNR — Class A+B hotels (cumulative)
    # saas_mrr_class_c == saas_mrr (all active A+B+C)
    mrr_growth_rate: Optional[float] = None                  # #8 MRR Growth Rate
    # ── Tier 2 · Engine — Monetisation ──────────────────────────────────────
    avg_aov: Optional[float] = None                          # #10 AOV
    orders_per_guest: Optional[float] = None                 # #11 Orders per Guest
    avg_arpg: Optional[float] = None                         # #12 Revenue per Guest (ARPG)
    revenue_per_booking: Optional[float] = None              # #13 Revenue per Booking
    category_mix_cars: Optional[float] = None                # #14 Category Mix – Cars %
    category_mix_transfers: Optional[float] = None           # #14 Category Mix – Transfers %
    category_mix_experiences: Optional[float] = None         # #14 Category Mix – Experiences %
    category_mix_wellness: Optional[float] = None            # #14 Category Mix – Wellness %
    category_mix_other: Optional[float] = None               # #14 Category Mix – Other %
    vertical_breakdown: Optional[dict] = None               # raw col-C verticals {name:{gmv,revenue,gmv_pct,revenue_pct}}
    # ── Purchase Channel ────────────────────────────────────────────────────
    direct_gmv: Optional[float] = None                       # GMV from Catalog source
    direct_revenue: Optional[float] = None                   # BG net revenue from Catalog
    concierge_gmv: Optional[float] = None                    # GMV from Offer source
    concierge_revenue: Optional[float] = None                # BG net revenue from Offer
    direct_pct: Optional[float] = None                       # Direct as % of total GMV
    concierge_pct: Optional[float] = None                    # Concierge as % of total GMV
    # ── Revenue Segment ────────────────────────────────────────────────────
    bg_general_gmv: Optional[float] = None                   # GMV from non-Alsabini rows
    bg_general_revenue: Optional[float] = None               # Service Fees (col I) all rows
    alsabini_gmv: Optional[float] = None                     # GMV from Alsabini rows
    alsabini_revenue: Optional[float] = None                 # Alsabini Take (col K)
    bg_general_pct: Optional[float] = None                   # BG General as % of total GMV
    alsabini_pct: Optional[float] = None                     # Alsabini as % of total GMV
    # ── Tier 2 · Engine — Funnel ─────────────────────────────────────────────
    pre_arrival_attach_rate: Optional[float] = None          # #15 Pre-Arrival Attach Rate
    post_booking_attach_rate: Optional[float] = None         # #16 Post-Booking Attach Rate
    total_paid_transactions: Optional[int] = None            # #42 Paid Transactions
    total_bookings: Optional[int] = None                     # #43 Total Bookings
    total_offers_generated: Optional[int] = None             # Offers Generated
    avg_offers_conversion: Optional[float] = None            # Offers Conversion
    whatsapp_conversion_uplift: Optional[float] = None       # #18 WhatsApp Conversion Uplift
    orders_per_day: Optional[float] = None                   # #19 Orders per Day
    # ── Tier 3 · Repeatability ───────────────────────────────────────────────
    attach_rate_variance: Optional[float] = None             # #23 Attach Rate Variance
    arpar_variance: Optional[float] = None                   # #24 ARPAR Variance
    pct_catalogue_active: Optional[float] = None             # #25 % Catalogue Active
    fill_rate: Optional[float] = None                        # #26 Fill Rate
    transactions_per_room_per_day: Optional[float] = None    # #27 Txns/Room/Day
    # ── Tier 4 · Scale ───────────────────────────────────────────────────────
    new_active_hotels: Optional[int] = None                  # #30 New Active Hotels Added
    revenue_per_hotel_per_month: Optional[float] = None      # #31 Revenue/Hotel/Month
    expansion_revenue: Optional[float] = None                # #33 Expansion Revenue
    expansion_rate: Optional[float] = None                   # #34 Expansion Rate
    onboarded_to_active_rate: Optional[float] = None         # #36 Onboarded→Active %
    nrr: Optional[float] = None                              # #37 Net Revenue Retention
    hotels_in_pipeline: Optional[int] = None                 # #49 Hotels in Pipeline
    # ── Tier 5 · Efficiency ──────────────────────────────────────────────────
    ltv_cac_ratio: Optional[float] = None                    # #40 LTV:CAC
    cac_payback_months: Optional[float] = None               # #41 CAC Payback Period
    avg_cac: Optional[float] = None                          # #42 CAC per Hotel
    hotel_ltv: Optional[float] = None                        # #43 Hotel LTV
    avg_time_to_activate: Optional[float] = None             # #46 Time to Activate (days)
    gross_margin_pct: Optional[float] = None                 # #47 Gross Margin %
    revenue_per_employee: Optional[float] = None             # #48 Revenue per Employee
    # ── Financial ────────────────────────────────────────────────────────────
    cash_balance: Optional[float] = None
    runway_months: Optional[float] = None
    monthly_burn_rate: Optional[float] = None


class HotelTrend(BaseModel):
    week_start_date: date
    gmv: float
    transactions: int
    net_revenue: float
    take_rate: float
    attach_rate: float
    prev_gmv: Optional[float] = None          # same week-of-year, prior year (364 days earlier)
    prev_net_revenue: Optional[float] = None
    prev_transactions: Optional[int] = None


class HotelDetailOut(BaseModel):
    hotel: HotelOut
    kpis: HotelKPIs
    trend: List[HotelTrend]


class PortfolioTrendPoint(BaseModel):
    week_start_date: str
    gmv: float
    net_revenue: float
    prev_net_revenue: Optional[float] = None   # same week last season (364 days back)
    alsabini_revenue: Optional[float] = None   # Alsabini Take, summed for the week
    cancellations: Optional[int] = None        # Count of Cancelled-status bookings that week
    cancellation_rate: Optional[float] = None  # cancellations / (transactions + cancellations) * 100
    transactions: int
    aov: float
    attach_rate: float
    active_hotels: int
    active_hotels_class_a: int = 0   # Class A only
    active_hotels_class_b: int = 0   # Class B only (not cumulative)
    active_hotels_class_c: int = 0   # Class C only (not cumulative)
    rooms_live: int = 0
    rooms_class_a: int = 0           # Rooms in Class A hotels
    rooms_class_b: int = 0           # Rooms in Class B hotels only
    rooms_class_c: int = 0           # Rooms in Class C hotels only
    # Per-class transactions (for monthly attach-rate aggregation in the frontend)
    txns_class_a: int = 0            # Transactions from Class A hotels only
    txns_class_ab: int = 0           # Transactions from Class A+B hotels
    # Per-class weekly attach rates (pre-computed; A+B+C = existing attach_rate)
    attach_rate_class_a: float = 0.0   # Class A only  (txns_a / rooms_a × 100)
    attach_rate_class_ab: float = 0.0  # Class A+B inclusive (txns_ab / rooms_ab × 100)


class MonthlyAttachRatePoint(BaseModel):
    month: str              # "2025-03"
    label: str              # "Mar '25"
    attach_rate_a: float    # Class A only
    attach_rate_ab: float   # Class A+B inclusive
    attach_rate_abc: float  # All active (A+B+C)
    txns_a: int
    txns_ab: int
    txns_abc: int


class VendorStat(BaseModel):
    vendor: str
    bookings: int
    gmv: float


class ProductStat(BaseModel):
    product: str
    bookings: int
    gmv: float


class UploadResult(BaseModel):
    rows_parsed: int
    rows_inserted: int
    errors: List[str] = []
    warnings: List[str] = []
