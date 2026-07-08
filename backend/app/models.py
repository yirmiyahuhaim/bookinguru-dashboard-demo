from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Hotel(Base):
    __tablename__ = "hotel_master"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    market = Column(String, nullable=False)          # e.g. Ibiza, Canary Islands
    property_type = Column(String, nullable=False)   # Boutique, Resort, City Hotel
    room_count = Column(Integer, nullable=False)
    seasonality = Column(String)                     # Year-round, Summer, Winter
    pipeline_status = Column(String, default="Active")  # Active, Pipeline, Churned
    saas_mrr = Column(Float, default=0.0)            # Monthly SaaS fee in EUR
    hubspot_id = Column(String, unique=True, nullable=True)
    # ── Tier 4 / 5 Scale & Efficiency ───────────────────────────────────────
    date_signed = Column(Date, nullable=True)               # Contract signed date
    date_activated = Column(Date, nullable=True)            # First reached 30 bookings/month
    cac = Column(Float, nullable=True)                      # Customer Acquisition Cost €
    is_chain_expansion = Column(Boolean, default=False)     # Signed as 2nd+ property in chain
    is_alsabini = Column(Boolean, default=False)            # Hotel is part of the Alsabini portfolio
    show_in_dashboard = Column(Boolean, server_default='true', default=True)  # Listed in "Active Hotel KPI" sheet tab
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    performances = relationship("WeeklyPerformance", back_populates="hotel")


class WeeklyPerformance(Base):
    __tablename__ = "weekly_performance"

    id = Column(Integer, primary_key=True, index=True)
    hotel_id = Column(Integer, ForeignKey("hotel_master.id"), nullable=False, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    gmv = Column(Float, default=0.0)                 # Gross Merchandise Value EUR
    transactions = Column(Integer, default=0)        # Paid bookings via BG
    free_transactions = Column(Integer, default=0)   # Free/comp bookings via BG
    avg_cart_value = Column(Float, default=0.0)      # AOV: GMV / transactions
    take_rate = Column(Float, default=0.0)           # BG commission %
    bg_gross_revenue = Column(Float, default=0.0)    # GMV * take_rate
    total_hotel_checkins = Column(Integer, default=0)
    incremental_revenue = Column(Float, nullable=True)   # Avg monthly ancillary revenue attributable to BG
    direct_booking_uplift = Column(Float, nullable=True) # Direct booking uplift %
    offers_generated = Column(Integer, nullable=True)    # Offers generated this week
    offers_conversion = Column(Float, nullable=True)     # % of offers that converted
    # ── Tier 2 Funnel / Monetisation ────────────────────────────────────────
    unique_guests = Column(Integer, nullable=True)          # Unique buying guests (→ Orders/Guest, ARPG)
    pre_arrival_bookings = Column(Integer, nullable=True)   # Bookings 1-7 days before check-in
    post_booking_bookings = Column(Integer, nullable=True)  # Bookings immediately post-confirmation
    whatsapp_bookings = Column(Integer, nullable=True)      # Bookings via WhatsApp channel
    email_bookings = Column(Integer, nullable=True)         # Bookings via email channel (baseline)
    cancellation_rate = Column(Float, nullable=True)        # Hotel cancellation rate %
    cancelled_transactions = Column(Integer, nullable=True) # Count of Cancelled-status bookings that week
    # ── Tier 3 Supply Quality ────────────────────────────────────────────────
    catalogue_total = Column(Integer, nullable=True)        # Total services listed
    catalogue_active = Column(Integer, nullable=True)       # Services with ≥1 booking in period
    booking_attempts = Column(Integer, nullable=True)       # Total booking attempts (incl. failed)
    # ── Category Mix ─────────────────────────────────────────────────────────
    cars_gmv = Column(Float, nullable=True)
    transfers_gmv = Column(Float, nullable=True)
    experiences_gmv = Column(Float, nullable=True)
    wellness_gmv = Column(Float, nullable=True)
    other_gmv = Column(Float, nullable=True)
    # ── Purchase Channel ─────────────────────────────────────────────────────
    direct_gmv      = Column(Float, nullable=True)   # Catalog / Catalogue source
    direct_revenue  = Column(Float, nullable=True)   # BG net revenue from direct
    concierge_gmv      = Column(Float, nullable=True)   # Offer source
    concierge_revenue  = Column(Float, nullable=True)   # BG net revenue from concierge
    # ── Revenue Segment ──────────────────────────────────────────────────────
    bg_general_gmv      = Column(Float, nullable=True)   # GMV where Alsabini Take = 0 (col K absent)
    bg_general_revenue  = Column(Float, nullable=True)   # Service Fees (col I) for ALL rows
    alsabini_gmv        = Column(Float, nullable=True)   # GMV where Alsabini Take > 0 (col K present)
    alsabini_revenue    = Column(Float, nullable=True)   # Alsabini Take (col K) for Alsabini rows
    vertical_breakdown  = Column(Text, nullable=True)    # JSON: {raw_vertical: {gmv, revenue}}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    hotel = relationship("Hotel", back_populates="performances")


class DailyBooking(Base):
    """
    One row per individual booking from the Sales 2025 / Sales 2026 Google Sheet tabs.
    Keyed on booking_ref — upserted on every Sync Sheets run.
    """
    __tablename__ = "daily_bookings"

    id                     = Column(Integer, primary_key=True, index=True)
    booking_ref            = Column(String, unique=True, nullable=False, index=True)
    hotel_id               = Column(Integer, ForeignKey("hotel_master.id"), nullable=True, index=True)
    hotel_name_raw         = Column(String, nullable=True)          # raw name from sheet
    reservation_date       = Column(Date, nullable=False, index=True)
    vertical_name          = Column(String, nullable=True)          # cruises / outdoors / …
    product_name           = Column(String, nullable=True, index=True)   # grouped in top-products
    product_option         = Column(String, nullable=True)
    service_date           = Column(Date, nullable=True)            # date of the actual service
    payment_method         = Column(String, nullable=True)          # Cash / CreditCard
    total_paid             = Column(Float, default=0.0)             # GMV €
    service_fees           = Column(Float, default=0.0)             # BG commission €
    alsabini_take          = Column(Float, default=0.0)             # Alsabini commission € (2026+)
    reservation_status     = Column(String, nullable=True)          # Completed / Cancelled / …
    payment_status         = Column(String, nullable=True)          # Paid / Unpaid / …
    provider_payout        = Column(Float, nullable=True)           # Amount paid to provider €
    offered_commission_eur = Column(Float, nullable=True)           # Commission € offered
    offered_commission_pct = Column(Float, nullable=True)           # Commission % offered
    company_name           = Column(String, nullable=True, index=True)   # Vendor — filtered/grouped in vendor queries
    source_channel         = Column(String, nullable=True)          # "direct" / "concierge"
    data_year              = Column(Integer, nullable=True)         # 2025 or 2026
    created_at             = Column(DateTime(timezone=True), server_default=func.now())

    hotel = relationship("Hotel", backref="daily_bookings")


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    cash_balance = Column(Float, default=0.0)        # EUR
    monthly_burn_rate = Column(Float, default=0.0)   # trailing 30-day avg spend EUR
    runway_months = Column(Float, default=0.0)       # cash_balance / monthly_burn_rate
    total_saas_mrr = Column(Float, default=0.0)      # sum of all active hotel SaaS fees
    source = Column(String, default="manual")        # manual, revolut_api
    # ── Tier 5 Efficiency ────────────────────────────────────────────────────
    headcount = Column(Integer, nullable=True)            # Total employees
    cogs = Column(Float, nullable=True)                   # Cost of goods sold for period €
    sales_marketing_cost = Column(Float, nullable=True)   # Monthly S&M spend €
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AlertSubscriber(Base):
    """Email addresses registered to receive milestone/threshold alerts."""
    __tablename__ = "alert_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AlertState(Base):
    """
    Key/value store for alert de-duplication — remembers which one-time
    milestones have fired (so we don't re-alert) and the last evaluated week.
    """
    __tablename__ = "alert_state"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
