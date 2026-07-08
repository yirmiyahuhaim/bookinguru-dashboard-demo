import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .database import engine, Base, is_sqlite
from .routers import hotels, performance, financial, upload, reports, analytics, alerts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Schema migrations: ADD COLUMN IF NOT EXISTS for all new columns ──────────
_MIGRATIONS = [
    # weekly_performance
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS unique_guests INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS pre_arrival_bookings INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS post_booking_bookings INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS whatsapp_bookings INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS email_bookings INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS cancellation_rate FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS cancelled_transactions INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS catalogue_total INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS catalogue_active INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS booking_attempts INTEGER",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS cars_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS transfers_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS experiences_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS wellness_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS other_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS direct_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS direct_revenue FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS concierge_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS concierge_revenue FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS bg_general_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS bg_general_revenue FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS alsabini_gmv FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS alsabini_revenue FLOAT",
    "ALTER TABLE weekly_performance ADD COLUMN IF NOT EXISTS vertical_breakdown TEXT",
    # hotel_master
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS date_signed DATE",
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS date_activated DATE",
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS cac FLOAT",
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS is_chain_expansion BOOLEAN DEFAULT FALSE",
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS is_alsabini BOOLEAN DEFAULT FALSE",
    "ALTER TABLE hotel_master ADD COLUMN IF NOT EXISTS show_in_dashboard BOOLEAN DEFAULT TRUE",
    # financial_snapshots
    "ALTER TABLE financial_snapshots ADD COLUMN IF NOT EXISTS headcount INTEGER",
    "ALTER TABLE financial_snapshots ADD COLUMN IF NOT EXISTS cogs FLOAT",
    "ALTER TABLE financial_snapshots ADD COLUMN IF NOT EXISTS sales_marketing_cost FLOAT",
    # daily_bookings — columns added after initial table creation
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS vertical_name TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS product_name TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS product_option TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS service_date DATE",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS payment_method TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS service_fees FLOAT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS alsabini_take FLOAT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS reservation_status TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS payment_status TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS provider_payout FLOAT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS offered_commission_eur FLOAT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS offered_commission_pct FLOAT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS company_name TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS source_channel TEXT",
    "ALTER TABLE daily_bookings ADD COLUMN IF NOT EXISTS data_year INTEGER",
    # Indexes for the vendor/product queries (filtered & grouped on these columns)
    "CREATE INDEX IF NOT EXISTS ix_daily_bookings_company_name ON daily_bookings (company_name)",
    "CREATE INDEX IF NOT EXISTS ix_daily_bookings_product_name ON daily_bookings (product_name)",
]


def _run_migrations():
    with engine.connect() as conn:
        for sql in _MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration note: {e}")


try:
    if os.getenv("RECREATE_TABLES", "false").lower() == "true":
        logger.info("RECREATE_TABLES=true — dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    logger.info("Database tables created/verified successfully.")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

app = FastAPI(
    title="BookinGuru Investor Dashboard API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With", "X-Internal-Token"],
)

# Gzip JSON responses — shrinks the larger payloads (hotels list, trends, matrix)
# and speeds transfer, especially on slower connections.
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(hotels.router, prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(financial.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bookinguru-dashboard"}


# ── Auto-sync: pull fresh bookings from the Reports API every N seconds ──────
# Active only when BOOKINGURU_REPORTS_API_KEY is set (API mode) and AUTO_SYNC
# isn't disabled. Runs in a daemon thread; overlapping runs are prevented by
# the sync lock in routers/upload.py. Also fires once shortly after startup,
# so the dashboard has fresh data immediately after a (re)deploy or cold start.
# Note: on Render's free tier the service sleeps when idle — the loop only
# runs while the service is awake (the startup sync covers wake-ups).

def _start_auto_sync():
    import threading
    import time as _time

    interval = int(os.getenv("AUTO_SYNC_INTERVAL_SECONDS", "300"))  # default 5 min

    def loop():
        _time.sleep(20)  # let the app finish booting first
        while True:
            try:
                from .services.api_sync import is_configured
                if is_configured() and os.getenv("AUTO_SYNC", "true").lower() == "true":
                    from .routers.upload import _run_sync_background
                    logger.info("Auto-sync: starting scheduled data sync")
                    _run_sync_background()
            except Exception as exc:
                logger.error(f"Auto-sync failed: {exc}")
            _time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="auto-sync").start()


_start_auto_sync()
