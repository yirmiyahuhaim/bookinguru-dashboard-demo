"""
Run: python seed_data.py
Populates the database with realistic demo data for the BookinGuru MVP.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta
import random
from app.database import SessionLocal, engine
from app.models import Base, Hotel, WeeklyPerformance, FinancialSnapshot, DailyBooking

Base.metadata.create_all(bind=engine)
db = SessionLocal()

random.seed(42)

# Vendors bookings are attributed to (Column Q equivalent) — feeds Top
# Vendors, Weekly Vendor Breakdown, and the per-hotel Vendor Portfolio.
VENDOR_POOL = [
    ("Sunset Boat Tours",        "cruises",  "Ibiza Sunset Cruise"),
    ("Blue Horizon Charters",    "cruises",  "Private Yacht Charter"),
    ("Island Bike Rentals",      "cars",     "Mountain Bike Rental (Daily)"),
    ("Turbo Rent a Car",         "cars",     "Economy Car Rental"),
    ("AquaVenture Diving",       "outdoors", "Scuba Diving Experience"),
    ("Coastal Kayak Adventures", "outdoors", "Sea Cave Kayak Tour"),
    ("Ibiza Wellness Spa",       "wellness", "Full Body Massage"),
    ("Sunrise Yoga Co",          "wellness", "Beach Yoga Session"),
    ("Local Flavors Food Tours", "other",    "Old Town Food Walk"),
    ("Skyline Helicopter Tours", "other",    "Island Helicopter Tour"),
]

HOTELS = [
    {"name": "Hotel Atzaró Agroturismo", "market": "Ibiza", "property_type": "Boutique", "room_count": 24, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 349.0},
    {"name": "Gran Hotel Montesol Ibiza", "market": "Ibiza", "property_type": "City Hotel", "room_count": 33, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 349.0},
    {"name": "Hotel Hacienda Na Xamena", "market": "Ibiza", "property_type": "Resort", "room_count": 77, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 499.0},
    {"name": "Ushuaïa Ibiza Beach Hotel", "market": "Ibiza", "property_type": "Resort", "room_count": 115, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 699.0},
    {"name": "Hotel Rural Can Lluc", "market": "Ibiza", "property_type": "Boutique", "room_count": 18, "seasonality": "Summer", "pipeline_status": "Pipeline", "saas_mrr": 0.0},
    {"name": "Hotel Jardín Tropical", "market": "Canary Islands", "property_type": "Resort", "room_count": 420, "seasonality": "Year-round", "pipeline_status": "Active", "saas_mrr": 999.0},
    {"name": "Barceló Tenerife", "market": "Canary Islands", "property_type": "Resort", "room_count": 380, "seasonality": "Year-round", "pipeline_status": "Active", "saas_mrr": 999.0},
    {"name": "Hotel Gran Tacande", "market": "Canary Islands", "property_type": "Boutique", "room_count": 74, "seasonality": "Year-round", "pipeline_status": "Active", "saas_mrr": 499.0},
    {"name": "Iberostar Founty Beach", "market": "Canary Islands", "property_type": "Resort", "room_count": 211, "seasonality": "Year-round", "pipeline_status": "Active", "saas_mrr": 699.0},
    {"name": "Hotel San Roque", "market": "Canary Islands", "property_type": "Boutique", "room_count": 20, "seasonality": "Year-round", "pipeline_status": "Pipeline", "saas_mrr": 0.0},
    {"name": "Palacio de los Leones", "market": "Mallorca", "property_type": "Boutique", "room_count": 28, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 349.0},
    {"name": "Hotel Formentor Mallorca", "market": "Mallorca", "property_type": "Resort", "room_count": 130, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 699.0},
    {"name": "Son Brull Hotel", "market": "Mallorca", "property_type": "Boutique", "room_count": 23, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 349.0},
    {"name": "Cap Rocat Hotel", "market": "Mallorca", "property_type": "Boutique", "room_count": 30, "seasonality": "Summer", "pipeline_status": "Churned", "saas_mrr": 0.0},
    {"name": "Hotel Costa d'Or", "market": "Mallorca", "property_type": "City Hotel", "room_count": 55, "seasonality": "Summer", "pipeline_status": "Active", "saas_mrr": 399.0},
]

print("Seeding hotels...")
hotel_objs = []
for h in HOTELS:
    existing = db.query(Hotel).filter(Hotel.name == h["name"]).first()
    if not existing:
        obj = Hotel(**h)
        db.add(obj)
        db.flush()
        hotel_objs.append(obj)
    else:
        hotel_objs.append(existing)
db.commit()

print("Seeding weekly performance (52 weeks per active hotel)...")
# Generate 52 weeks of data ending today
today = date.today()
week_starts = [today - timedelta(weeks=i) for i in range(51, -1, -1)]

# Take rate bands per market
TAKE_RATES = {"Ibiza": (12.0, 16.0), "Canary Islands": (10.0, 14.0), "Mallorca": (11.0, 15.0)}

booking_idx = 0
for hotel in hotel_objs:
    if hotel.pipeline_status == "Churned":
        # only 8 weeks of history
        weeks = week_starts[-8:]
    elif hotel.pipeline_status == "Pipeline":
        # no performance data yet
        continue
    else:
        weeks = week_starts

    tr_low, tr_high = TAKE_RATES.get(hotel.market, (10.0, 15.0))

    # Each hotel works with a random subset of vendors, one clearly dominant
    # (mirrors real concentration — a couple of vendors driving most volume).
    hotel_vendors = random.sample(VENDOR_POOL, k=random.randint(4, 8))
    hotel_vendor_weights = [3.0] + [1.0] * (len(hotel_vendors) - 1)
    random.shuffle(hotel_vendor_weights)

    # Attach Rate = total bookings over the period ÷ room count (see
    # kpi_engine.get_hotel_kpis) — target a believable range over the full
    # season so the dashboard's own coloring thresholds (>=15% "strong")
    # land somewhere sane instead of blowing past 1000%. The floor keeps
    # even small hotels lively enough to populate weekly/vendor charts.
    season_target = max(15, round(hotel.room_count * random.uniform(0.30, 0.80)))

    # Seasonal weight per week, used both to distribute bookings and (below)
    # to keep GMV in the same rhythm.
    season_weights = []
    for ws in weeks:
        month = ws.month
        if hotel.seasonality == "Summer":
            w = 1.0 + 0.8 * max(0, (month - 4) / 4) if 5 <= month <= 9 else 0.3
        elif hotel.seasonality == "Winter":
            w = 1.0 + 0.5 * (1 - abs(month - 1) / 6) if month <= 3 or month >= 10 else 0.4
        else:
            w = 0.9 + 0.2 * random.random()
        season_weights.append(w)
    total_weight = sum(season_weights)

    for i, ws in enumerate(weeks):
        seasonal = season_weights[i]
        growth   = 1 + (i / len(weeks)) * 0.4  # gentle upward trend over the season

        # Probabilistic rounding so the season-long total lands near
        # season_target while individual weeks vary (including some zeros).
        expected = season_target * (seasonal / total_weight) * growth
        transactions = int(expected) + (1 if random.random() < (expected - int(expected)) else 0)

        take_rate = random.uniform(tr_low, tr_high)
        avg_cart  = random.uniform(90, 350)
        gmv       = transactions * avg_cart * random.uniform(0.85, 1.15)
        checkins  = max(transactions, int(transactions / random.uniform(0.05, 0.25))) if transactions else 0
        bg_revenue = gmv * (take_rate / 100)

        existing = db.query(WeeklyPerformance).filter(
            WeeklyPerformance.hotel_id == hotel.id,
            WeeklyPerformance.week_start_date == ws
        ).first()
        if not existing:
            db.add(WeeklyPerformance(
                hotel_id=hotel.id,
                week_start_date=ws,
                gmv=round(gmv, 2),
                transactions=transactions,
                avg_cart_value=round(avg_cart, 2),
                take_rate=round(take_rate, 2),
                bg_gross_revenue=round(bg_revenue, 2),
                total_hotel_checkins=checkins,
            ))

            # One DailyBooking per counted transaction — feeds the vendor
            # breakdown widgets (Top Vendors, Weekly Vendor Breakdown,
            # Vendor Portfolio for Given Hotel).
            for b in range(transactions):
                vendor, vertical, product = random.choices(hotel_vendors, weights=hotel_vendor_weights)[0]
                booking_total = round(avg_cart * random.uniform(0.7, 1.3), 2)
                booking_fee   = round(booking_total * (take_rate / 100), 2)
                booking_idx  += 1
                db.add(DailyBooking(
                    booking_ref=f"DEMO-{hotel.id}-{booking_idx}",
                    hotel_id=hotel.id,
                    hotel_name_raw=hotel.name,
                    reservation_date=ws + timedelta(days=random.randint(0, 6)),
                    vertical_name=vertical,
                    product_name=product,
                    total_paid=booking_total,
                    service_fees=booking_fee,
                    reservation_status="Cancelled" if random.random() < 0.04 else "Completed",
                    payment_status="Paid",
                    company_name=vendor,
                    source_channel=random.choice(["direct", "concierge"]),
                    data_year=ws.year,
                ))

db.commit()

print("Seeding financial snapshots (12 months)...")
cash = 1_450_000.0
burn = 95_000.0
for m in range(11, -1, -1):
    snap_date = date(today.year, today.month, 1) - timedelta(days=30 * m)
    runway = cash / burn if burn else 0
    total_mrr = sum(h.saas_mrr for h in hotel_objs if h.pipeline_status == "Active")
    existing = db.query(FinancialSnapshot).filter(
        FinancialSnapshot.snapshot_date == snap_date
    ).first()
    if not existing:
        db.add(FinancialSnapshot(
            snapshot_date=snap_date,
            cash_balance=round(cash, 2),
            monthly_burn_rate=round(burn, 2),
            runway_months=round(runway, 1),
            total_saas_mrr=round(total_mrr, 2),
            source="manual",
        ))
    cash -= burn * random.uniform(0.9, 1.1)
    burn += random.uniform(-3000, 5000)

db.commit()
db.close()
print("Done! Database seeded successfully.")
