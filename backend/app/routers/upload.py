from difflib import SequenceMatcher

import os
import secrets
import threading
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, HTTPException, Header
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..schemas import UploadResult
from ..services.parser import parse_xlsx, parse_csv
from ..services.reconciliation import reconcile_and_insert
from ..services.room_seeder import process_room_counts
from ..services.sheets_sync import (
    sync_all_from_sheets,
    sync_all_parallel,
    sync_room_counts_from_sheets,
)
from ..models import Hotel, WeeklyPerformance, FinancialSnapshot, DailyBooking
from ..auth import require_auth


def _name_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/weekly-kpi", response_model=UploadResult)
async def upload_weekly_kpi(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        records, errors = parse_xlsx(content)
    elif filename.endswith(".csv"):
        records, errors = parse_csv(content)
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Please upload .xlsx or .csv"
        )

    if errors and not records:
        return UploadResult(rows_parsed=0, rows_inserted=0, errors=errors)

    result = reconcile_and_insert(db, records)
    result.errors = errors + result.errors
    return result


@router.post("/hotel-meta")
async def upload_hotel_meta(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Upload a hotel list Excel (ALSABINI-style) to sync room counts.
    Fuzzy-matches hotel names and updates room_count in the DB.
    """
    if not (file.filename or "").endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=415, detail="Please upload an .xlsx file")
    content = await file.read()
    result = process_room_counts(content, db)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


_sync_state: dict = {"status": "idle", "warnings": [], "errors": []}
_sync_lock = threading.Lock()   # prevents overlapping runs (manual vs 5-min auto-sync)


def _run_sync_background():
    """Run the full data sync in a background thread with its own DB session."""
    global _sync_state
    if not _sync_lock.acquire(blocking=False):
        return  # a sync is already running — skip this trigger
    _sync_state = {"status": "running", "warnings": [], "errors": []}
    db = SessionLocal()
    try:
        _do_sync(db)
        _sync_state["status"] = "done"
    except Exception as exc:
        _sync_state["status"] = "error"
        _sync_state["errors"].append(str(exc))
    finally:
        db.close()
        _sync_lock.release()


@router.post("/sync-sheets")
def sync_from_sheets(
    background_tasks: BackgroundTasks,
    _: str = Depends(require_auth),
):
    """
    Kick off a background sync from Google Sheets and return immediately.
    The actual import runs in a background thread (can take 2-4 minutes).
    """
    background_tasks.add_task(_run_sync_background)
    return {"status": "started", "message": "Sync started — data will be ready in ~2 minutes. Refresh the page then."}


@router.post("/scheduled-sync", status_code=202)
def scheduled_sync(
    background_tasks: BackgroundTasks,
    x_sync_token: str = Header(default=""),
):
    """
    Token-protected sync trigger for the weekly scheduler (GitHub Actions).
    Authenticate with header `X-Sync-Token: <SYNC_TOKEN>` (set SYNC_TOKEN in the
    backend env). Runs the same background sync as /sync-sheets, which evaluates
    and emails alerts at the end.
    """
    expected = os.getenv("SYNC_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Scheduled sync not configured (SYNC_TOKEN unset).")
    if not x_sync_token or not secrets.compare_digest(x_sync_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid sync token.")
    background_tasks.add_task(_run_sync_background)
    return {"status": "started", "trigger": "scheduled"}


_WEEKLY_FIELDS = [
    "gmv", "transactions", "take_rate", "bg_gross_revenue", "avg_cart_value",
    "cars_gmv", "transfers_gmv", "experiences_gmv", "wellness_gmv", "other_gmv",
    "cancellation_rate", "cancelled_transactions", "direct_gmv", "direct_revenue", "concierge_gmv",
    "concierge_revenue", "bg_general_gmv", "bg_general_revenue",
    "alsabini_gmv", "alsabini_revenue", "vertical_breakdown",
]


def _merge_alias_hotels(db: Session, alias_map: dict, warnings: list, errors: list):
    """
    Fold existing alias hotel records into their canonical main hotel, per the
    Hotel Aliases tab. Reassigns daily bookings to the main hotel, removes the
    alias hotel's weekly rows (rebuilt under the main name from the sheet on this
    same sync), and deletes the alias hotel. Idempotent — once merged, the alias
    hotel no longer exists, so later syncs are no-ops.
    """
    if not alias_map:
        return
    try:
        hotels = {h.name.strip().lower(): h for h in db.query(Hotel).all()}
        merged = []
        for alias_lower, main_name in alias_map.items():
            alias_hotel = hotels.get(alias_lower)
            if alias_hotel is None:
                continue  # nothing stored under this alias
            main_lower = main_name.strip().lower()
            if main_lower == alias_lower:
                continue
            main_hotel = hotels.get(main_lower)
            if main_hotel is None:
                # Promote the alias record itself to the main name (cheapest merge)
                alias_hotel.name = main_name
                db.query(DailyBooking).filter(func.lower(DailyBooking.hotel_name_raw) == alias_lower).update(
                    {DailyBooking.hotel_name_raw: main_name}, synchronize_session=False,
                )
                hotels[main_lower] = alias_hotel
                del hotels[alias_lower]
                merged.append(main_name)
                continue
            # Reassign this alias's bookings to the main hotel (by id and by raw name)
            db.query(DailyBooking).filter(DailyBooking.hotel_id == alias_hotel.id).update(
                {DailyBooking.hotel_id: main_hotel.id, DailyBooking.hotel_name_raw: main_name},
                synchronize_session=False,
            )
            db.query(DailyBooking).filter(func.lower(DailyBooking.hotel_name_raw) == alias_lower).update(
                {DailyBooking.hotel_id: main_hotel.id, DailyBooking.hotel_name_raw: main_name},
                synchronize_session=False,
            )
            # Drop the alias hotel's weekly rows (FK) — rebuilt under main from the sheet
            db.query(WeeklyPerformance).filter(WeeklyPerformance.hotel_id == alias_hotel.id).delete(
                synchronize_session=False,
            )
            db.delete(alias_hotel)
            del hotels[alias_lower]
            merged.append(main_name)
        if merged:
            db.commit()
            warnings.append(f"Merged {len(merged)} alias hotel(s) into their main name (Hotel Aliases tab).")
    except Exception as exc:
        db.rollback()
        errors.append(f"Hotel alias merge failed: {exc}")


def _do_sync(db: Session):
    """Full sync logic — runs in background with its own session."""
    global _sync_state
    # Bookings source: BookinGuru Reports API when configured (preferred),
    # otherwise fall back to the Google Sheets Sales tabs. Rooms + Aliases
    # always come from the sheet in both modes.
    from ..services import api_sync
    if api_sync.is_configured():
        records, daily_records, room_records, alias_map, fetch_errors = api_sync.sync_all_parallel_api()
    else:
        records, daily_records, room_records, alias_map, fetch_errors = sync_all_parallel()

    if not records and fetch_errors:
        _sync_state["errors"] = fetch_errors
        return

    errors   = list(fetch_errors)
    warnings = []

    # Merge any existing alias hotels into their main name BEFORE upserting, so
    # the canonicalized sheet data lands on one hotel record.
    _merge_alias_hotels(db, alias_map, warnings, errors)

    # ── Weekly performance upsert (bulk, not row-by-row) ─────────────────────
    # 1. Preload all existing hotels into a dict (one query)
    all_hotels  = db.query(Hotel).all()
    hotel_cache = {h.name.lower().strip(): h for h in all_hotels}

    # 2. Create missing hotels in bulk
    needed_names = {r["hotel_name"].lower().strip(): r["hotel_name"] for r in records}
    for key, raw_name in needed_names.items():
        if key not in hotel_cache:
            hotel = Hotel(
                name=raw_name,
                market="Unknown",
                property_type="Unknown",
                room_count=0,
                pipeline_status="Active",
            )
            db.add(hotel)
            hotel_cache[key] = hotel
    db.flush()  # assign IDs to new hotels in one round-trip

    # 3. Preload all existing WeeklyPerformance rows (one query)
    existing_wp = {
        (wp.hotel_id, wp.week_start_date): wp
        for wp in db.query(WeeklyPerformance).all()
    }

    # 4. Split into inserts vs updates
    to_insert: list = []
    updated = 0
    for rec in records:
        hotel = hotel_cache.get(rec["hotel_name"].lower().strip())
        if not hotel:
            continue
        key = (hotel.id, rec["week_start_date"])
        if key in existing_wp:
            wp = existing_wp[key]
            for f in _WEEKLY_FIELDS:
                setattr(wp, f, rec.get(f))
            updated += 1
        else:
            to_insert.append({
                "hotel_id":        hotel.id,
                "week_start_date": rec["week_start_date"],
                **{f: rec.get(f) for f in _WEEKLY_FIELDS},
            })

    if to_insert:
        db.bulk_insert_mappings(WeeklyPerformance, to_insert)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"DB commit failed: {exc}")
        return

    if updated:
        warnings.append(f"{updated} existing weekly rows updated.")
    if to_insert:
        warnings.append(f"{len(to_insert)} new weekly rows inserted.")

    # Re-read hotels so new ones (created above) are included
    all_hotels = list(hotel_cache.values())

    # ── Room counts sync (data already fetched in parallel above) ────────────
    if room_records:
        THRESHOLD     = 0.55
        rooms_updated = 0

        for hotel in all_hotels:
            best_score: float = 0.0
            best_entry: dict  = {}

            for entry in room_records:
                for xl_name in entry["names"]:
                    score = _name_sim(hotel.name, xl_name)
                    if score > best_score:
                        best_score = score
                        best_entry = entry

            if best_score >= THRESHOLD and best_entry:
                new_rooms = best_entry["rooms"]
                new_type  = best_entry.get("property_type")
                changed   = False

                if hotel.room_count != new_rooms:
                    hotel.room_count = new_rooms
                    changed = True
                if new_type and hotel.property_type in (None, "Unknown"):
                    hotel.property_type = new_type
                    changed = True

                if changed:
                    rooms_updated += 1

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            errors.append(f"Room count DB commit failed: {exc}")

        if rooms_updated:
            warnings.append(
                f"{rooms_updated} hotel room count(s) updated from Main KPIs sheet."
            )

    # All hotels derived from the Sales tabs are shown across the dashboard —
    # the Active Hotel KPI tab is no longer used to gate visibility.

    # ── Daily bookings sync (bulk upsert) ───────────────────────────────────
    if daily_records:
        # 1. Resolve hotel_ids using the already-loaded hotel_cache (no extra queries)
        daily_hotel_cache: dict = {k: h.id for k, h in hotel_cache.items()}

        # 2. Fetch all already-stored refs in one IN query
        all_refs = [r["booking_ref"] for r in daily_records]
        existing_id_map: dict = {
            row[0]: row[1]
            for row in db.query(DailyBooking.booking_ref, DailyBooking.id)
                         .filter(DailyBooking.booking_ref.in_(all_refs))
                         .all()
        }

        # 3. Split into inserts vs updates, deduplicating by booking_ref
        #    (duplicate refs in the sheet cause a UNIQUE violation on bulk insert)
        to_insert: dict = {}   # ref -> row_data
        to_update: list = []

        for rec in daily_records:
            hotel_id = daily_hotel_cache.get(rec["hotel_name_raw"].lower().strip())
            row_data = {
                "hotel_id":               hotel_id,
                "hotel_name_raw":         rec["hotel_name_raw"],
                "reservation_date":       rec["reservation_date"],
                "vertical_name":          rec["vertical_name"],
                "product_name":           rec["product_name"],
                "product_option":         rec["product_option"],
                "service_date":           rec["service_date"],
                "payment_method":         rec["payment_method"],
                "total_paid":             rec["total_paid"],
                "service_fees":           rec["service_fees"],
                "alsabini_take":          rec["alsabini_take"],
                "reservation_status":     rec["reservation_status"],
                "payment_status":         rec["payment_status"],
                "provider_payout":        rec["provider_payout"],
                "offered_commission_eur": rec["offered_commission_eur"],
                "offered_commission_pct": rec["offered_commission_pct"],
                "company_name":           rec["company_name"],
                "source_channel":         rec["source_channel"],
                "data_year":              rec["data_year"],
            }
            ref = rec["booking_ref"]
            if ref in existing_id_map:
                row_data["id"] = existing_id_map[ref]
                to_update.append(row_data)
            else:
                row_data["booking_ref"] = ref
                to_insert[ref] = row_data  # last occurrence wins for duplicates

        # Diagnostic: vendor coverage (helps debug Column Q mismatches)

        # 4. Bulk insert new rows, bulk update existing rows
        insert_list = list(to_insert.values())
        try:
            if insert_list:
                db.bulk_insert_mappings(DailyBooking, insert_list)
            if to_update:
                db.bulk_update_mappings(DailyBooking, to_update)
            db.commit()
            warnings.append(
                f"Daily bookings: {len(insert_list)} new, {len(to_update)} updated "
                f"({len(daily_records)} parsed, {len(daily_records) - len(insert_list) - len(to_update)} duplicate refs skipped)."
            )
        except Exception as exc:
            db.rollback()
            errors.append(f"Daily bookings DB commit failed: {exc}")

    # ── Recompute the Alsabini hotel flag from actual booking data ──────────
    # A hotel counts as "Alsabini" only if at least one of its bookings has
    # Alsabini S.A. as the vendor (Company Name / Column Q) — the same
    # provider check used for the Alsabini revenue segment split in Tier 2.
    # Recomputed in full on every sync (not accumulated) so a hotel that's no
    # longer associated with Alsabini stops showing up as one.
    try:
        alsabini_hotel_ids = {
            hid for (hid,) in db.query(DailyBooking.hotel_id)
                .filter(DailyBooking.hotel_id.isnot(None))
                .filter(func.upper(DailyBooking.company_name).like('ALSABINI%'))
                .distinct()
        }
        for hotel in db.query(Hotel).all():
            hotel.is_alsabini = hotel.id in alsabini_hotel_ids
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append(f"Alsabini hotel flag recompute failed: {exc}")

    # ── Evaluate + email milestone/threshold alerts after the weekly sync ────
    try:
        from ..services.alerts import run_alerts
        fired = run_alerts(db)
        if fired:
            warnings.append(f"Alerts: {len(fired)} fired — " + "; ".join(a["title"] for a in fired))
    except Exception as exc:
        errors.append(f"Alert evaluation failed: {exc}")

    # Write final result into shared state so the poll endpoint can report it
    _sync_state["warnings"] = warnings
    _sync_state["errors"]   = errors


@router.get("/sync-status")
def sync_status(_: str = Depends(require_auth)):
    """Return the current state of the background sync."""
    return _sync_state


@router.delete("/reset", status_code=200)
def reset_database(
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Wipe all performance, financial and hotel data. Use with caution."""
    deleted_perf = db.query(WeeklyPerformance).delete()
    deleted_fin  = db.query(FinancialSnapshot).delete()
    deleted_hotels = db.query(Hotel).delete()
    db.commit()
    return {
        "message": "Database cleared successfully.",
        "deleted": {
            "weekly_performance": deleted_perf,
            "financial_snapshots": deleted_fin,
            "hotels": deleted_hotels,
        }
    }
