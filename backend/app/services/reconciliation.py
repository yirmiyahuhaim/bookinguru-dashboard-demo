from sqlalchemy.orm import Session
from typing import List, Dict, Tuple
from ..models import Hotel, WeeklyPerformance
from ..schemas import UploadResult


def reconcile_and_insert(db: Session, records: List[Dict]) -> UploadResult:
    """
    Deduplicate incoming records against the canonical DB.
    Matches hotels by name (case-insensitive). Creates hotel stub if not found.
    Skips duplicate (hotel_id, week_start_date) combinations.
    """
    inserted = 0
    errors: List[str] = []
    warnings: List[str] = []

    hotel_cache: Dict[str, Hotel] = {}

    for rec in records:
        hotel_name = rec["hotel_name"]
        name_key = hotel_name.lower().strip()

        # resolve hotel
        if name_key not in hotel_cache:
            hotel = db.query(Hotel).filter(
                Hotel.name.ilike(hotel_name)
            ).first()
            room_count_from_rec = rec.get("room_count") or 0
            if not hotel:
                # create stub — operator can fill details later
                hotel = Hotel(
                    name=hotel_name,
                    market="Unknown",
                    property_type="Unknown",
                    room_count=room_count_from_rec,
                    pipeline_status="Active",
                )
                db.add(hotel)
                db.flush()
                warnings.append(
                    f"Created stub hotel '{hotel_name}' — please update market/type/rooms."
                )
            elif room_count_from_rec and hotel.room_count == 0:
                # update room count if previously unknown
                hotel.room_count = room_count_from_rec
                db.flush()
            hotel_cache[name_key] = hotel

        hotel = hotel_cache[name_key]

        # deduplication check
        existing = db.query(WeeklyPerformance).filter(
            WeeklyPerformance.hotel_id == hotel.id,
            WeeklyPerformance.week_start_date == rec["week_start_date"]
        ).first()

        if existing:
            warnings.append(
                f"Duplicate skipped: {hotel_name} week {rec['week_start_date']}"
            )
            continue

        perf = WeeklyPerformance(
            hotel_id=hotel.id,
            week_start_date=rec["week_start_date"],
            gmv=rec["gmv"],
            transactions=rec["transactions"],
            free_transactions=rec.get("free_transactions", 0),
            avg_cart_value=rec["avg_cart_value"],
            take_rate=rec["take_rate"],
            bg_gross_revenue=rec["bg_gross_revenue"],
            total_hotel_checkins=rec.get("total_hotel_checkins", 0),
            incremental_revenue=rec.get("incremental_revenue"),
            direct_booking_uplift=rec.get("direct_booking_uplift"),
            offers_generated=rec.get("offers_generated"),
            offers_conversion=rec.get("offers_conversion"),
            # New fields
            unique_guests=rec.get("unique_guests"),
            pre_arrival_bookings=rec.get("pre_arrival_bookings"),
            post_booking_bookings=rec.get("post_booking_bookings"),
            whatsapp_bookings=rec.get("whatsapp_bookings"),
            email_bookings=rec.get("email_bookings"),
            cancellation_rate=rec.get("cancellation_rate"),
            cancelled_transactions=rec.get("cancelled_transactions"),
            catalogue_total=rec.get("catalogue_total"),
            catalogue_active=rec.get("catalogue_active"),
            booking_attempts=rec.get("booking_attempts"),
            cars_gmv=rec.get("cars_gmv"),
            transfers_gmv=rec.get("transfers_gmv"),
            experiences_gmv=rec.get("experiences_gmv"),
            wellness_gmv=rec.get("wellness_gmv"),
            other_gmv=rec.get("other_gmv"),
            direct_gmv=rec.get("direct_gmv"),
            direct_revenue=rec.get("direct_revenue"),
            concierge_gmv=rec.get("concierge_gmv"),
            concierge_revenue=rec.get("concierge_revenue"),
            bg_general_gmv=rec.get("bg_general_gmv"),
            bg_general_revenue=rec.get("bg_general_revenue"),
            alsabini_gmv=rec.get("alsabini_gmv"),
            alsabini_revenue=rec.get("alsabini_revenue"),
            vertical_breakdown=rec.get("vertical_breakdown"),
        )
        db.add(perf)
        inserted += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"DB commit failed: {e}")
        inserted = 0

    return UploadResult(
        rows_parsed=len(records),
        rows_inserted=inserted,
        errors=errors,
        warnings=warnings,
    )
