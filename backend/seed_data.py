"""
Run: python seed_data.py
Populates the database with realistic synthetic demo data for the BookinGuru
dashboard.

To keep the demo a faithful mirror of the live application, this script does
NOT hand-write weekly summary rows. Instead it generates individual synthetic
bookings and runs them through the exact same aggregation the production sync
uses (app.services.api_sync.build_weekly_records). That means every
booking-derived view - cancellations, the partner (Alsabini) revenue segment,
purchase-channel splits, and the vertical breakdown - is computed the same way
it would be from real data, just from fictional bookings.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, timedelta
import random
from app.database import SessionLocal, engine
from app.models import Base, Hotel, WeeklyPerformance, FinancialSnapshot, DailyBooking
from app.services.api_sync import build_weekly_records

Base.metadata.create_all(bind=engine)
db = SessionLocal()

random.seed(42)

# Partner commission rate and cut-off, mirroring the production Alsabini logic.
PARTNER_TAKE_RATE = 0.05
PARTNER_SINCE = date(2026, 1, 1)

# General vendor pool: (company name, vertical, product). The vertical is
# mapped to a category by the same VERTICAL_MAP the production aggregation
# uses, so the vertical breakdown populates realistically.
VENDOR_POOL = [
    ("Sunset Boat Tours",        "cruises",        "Ibiza Sunset Cruise"),
    ("Blue Horizon Charters",    "cruises",        "Private Yacht Charter"),
    ("Island Bike Rentals",      "cars",           "Mountain Bike Rental (Daily)"),
    ("Turbo Rent a Car",         "cars",           "Economy Car Rental"),
    ("AquaVenture Diving",       "outdoors",       "Scuba Diving Experience"),
    ("Coastal Kayak Adventures", "outdoors",       "Sea Cave Kayak Tour"),
    ("Ibiza Wellness Spa",       "wellness",       "Full Body Massage"),
    ("Sunrise Yoga Co",          "wellness",       "Beach Yoga Session"),
    ("Local Flavors Food Tours", "food",           "Old Town Food Walk"),
    ("Skyline Helicopter Tours", "tours",          "Island Helicopter Tour"),
    ("Island Transfers Co",      "transportation", "Airport Transfer (Private)"),
    ("Ibiza Nightlife Access",   "nightlife",      "VIP Club Table"),
]

# A strategic commercial partner whose bookings carry an additional partner
# commission ("take"). This drives the Tier 2 revenue segment and the
# Alsabini / Non-Alsabini hotel filter.
PARTNER_VENDOR = ("Alsabini S.A.", "experiences", "Curated Experience Package")

# Hotels that transact with the strategic partner. Includes the two
# highest-volume resorts so the partner reads as a meaningful revenue segment.
PARTNER_HOTELS = {
    "Hotel Atzaró Agroturismo",
    "Ushuaïa Ibiza Beach Hotel",
    "Barceló Tenerife",
    "Hotel Formentor Mallorca",
    "Gran Hotel Montesol Ibiza",
    "Hotel Jardín Tropical",
    "Iberostar Founty Beach",
}

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

# Skip generation entirely if bookings already exist (idempotent re-runs).
if db.query(DailyBooking).count() == 0:
    print("Generating synthetic bookings...")
    today = date.today()
    week_starts = [today - timedelta(weeks=i) for i in range(51, -1, -1)]

    # Take rate bands per market (used as each booking's service-fee rate).
    TAKE_RATES = {"Ibiza": (12.0, 16.0), "Canary Islands": (10.0, 14.0), "Mallorca": (11.0, 15.0)}

    daily_records = []
    booking_idx = 0

    for hotel in hotel_objs:
        if hotel.pipeline_status == "Churned":
            weeks = week_starts[-8:]          # short, recent history only
        elif hotel.pipeline_status == "Pipeline":
            continue                          # signed but not yet transacting
        else:
            weeks = week_starts

        tr_low, tr_high = TAKE_RATES.get(hotel.market, (10.0, 15.0))
        is_partner = hotel.name in PARTNER_HOTELS

        # Each hotel works with a random subset of vendors, one clearly
        # dominant (mirrors real concentration). Partner hotels additionally
        # carry the strategic partner as a meaningful share of their bookings.
        base_vendors = random.sample(VENDOR_POOL, k=random.randint(4, 7))
        if is_partner:
            hotel_vendors = [PARTNER_VENDOR] + base_vendors
            weights = [4.5] + [1.0] * len(base_vendors)   # partner is dominant
        else:
            hotel_vendors = base_vendors
            weights = [3.0] + [1.0] * (len(base_vendors) - 1)
            random.shuffle(weights)

        # Target total bookings over the season, tuned so the dashboard's own
        # attach-rate thresholds land in a believable range.
        season_target = max(15, round(hotel.room_count * random.uniform(0.30, 0.80)))

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
            growth = 1 + (i / len(weeks)) * 0.4   # gentle upward trend

            expected = season_target * (seasonal / total_weight) * growth
            completed = int(expected) + (1 if random.random() < (expected - int(expected)) else 0)
            if completed <= 0:
                continue
            cancelled = sum(1 for _ in range(completed) if random.random() < 0.05)

            for status in (["Completed"] * completed + ["Cancelled"] * cancelled):
                vendor, vertical, product = random.choices(hotel_vendors, weights=weights)[0]
                rd = ws + timedelta(days=random.randint(0, 6))
                rate = random.uniform(tr_low, tr_high)
                total_paid = round(random.uniform(90, 350) * random.uniform(0.7, 1.3), 2)
                service_fee = round(total_paid * rate / 100, 2)
                partner_take = (
                    round(PARTNER_TAKE_RATE * (total_paid - service_fee), 2)
                    if vendor == PARTNER_VENDOR[0] and rd >= PARTNER_SINCE else 0.0
                )
                booking_idx += 1
                daily_records.append({
                    "booking_ref":        f"DEMO-{hotel.id}-{booking_idx}",
                    "hotel_id":           hotel.id,
                    "hotel_name_raw":     hotel.name,
                    "reservation_date":   rd,
                    "vertical_name":      vertical,
                    "product_name":       product,
                    "total_paid":         total_paid,
                    "service_fees":       service_fee,
                    "alsabini_take":      partner_take,
                    "reservation_status": status,
                    "payment_status":     "Paid",
                    "company_name":       vendor,
                    "source_channel":     random.choice(["direct", "concierge"]),
                    "data_year":          rd.year,
                })

    print(f"  generated {len(daily_records)} bookings; writing to database...")
    db.bulk_insert_mappings(DailyBooking, daily_records)
    db.commit()

    # Aggregate the bookings into weekly per-hotel rows using the SAME code
    # path production uses, so every derived field is computed identically.
    print("Aggregating weekly performance (production pipeline)...")
    errors = []
    weekly_records = build_weekly_records(daily_records, errors)
    name_to_id = {h.name: h.id for h in hotel_objs}
    wp_rows = []
    for rec in weekly_records:
        hid = name_to_id.get(rec["hotel_name"])
        if hid is None:
            continue
        row = {k: v for k, v in rec.items() if k != "hotel_name"}
        row["hotel_id"] = hid
        wp_rows.append(row)
    db.bulk_insert_mappings(WeeklyPerformance, wp_rows)
    db.commit()
    print(f"  wrote {len(wp_rows)} weekly performance rows.")

    # Recompute the partner (Alsabini) hotel flag from actual booking data,
    # exactly as the production sync does.
    partner_hotel_ids = {
        rec["hotel_id"] for rec in daily_records
        if (rec["company_name"] or "").upper().startswith("ALSABINI")
    }
    for hotel in hotel_objs:
        hotel.is_alsabini = hotel.id in partner_hotel_ids
    db.commit()
    print(f"  flagged {len(partner_hotel_ids)} hotels as strategic-partner (Alsabini) hotels.")
else:
    print("Bookings already present - skipping generation.")

print("Seeding financial snapshots (12 months)...")
today = date.today()
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
