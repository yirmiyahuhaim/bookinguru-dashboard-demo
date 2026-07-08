"""
BookinGuru Booking Reports API sync.

Replaces the Google-Sheets Sales-tab ingestion with direct API pulls from
BookinGuru's reporting endpoint (per the integration guide from the BookinGuru
dev team):

    GET https://app.bookinguru.com/api/reports/bookings
    header  x-api-key: <BOOKINGURU_REPORTS_API_KEY>
    params  from / to (ISO dates), page, limit (max 1000)

The Rooms, Hotel Aliases, and Forecast tabs still come from Google Sheets —
the API only covers bookings.

Field mapping (API → DailyBooking):
    referenceNumber      → booking_ref
    createdAt            → reservation_date (+ data_year)
    conciergeCompanyName → hotel_name_raw      (the "hotel" everywhere in the app)
    providerCompanyName  → company_name        (the "vendor")
    vertical             → vertical_name
    productName          → product_name
    variantName          → product_option
    startDateAndTime     → service_date
    paymentMethod        → payment_method
    totalPaid            → total_paid          (refund-adjusted by the API)
    serviceFees          → service_fees
    status               → reservation_status  (Completed / Cancelled)
    paymentStatus        → payment_status
    providerPayout       → provider_payout
    offeredCommission    → offered_commission_eur / _pct ("12.00 €" vs "15 %")
    source               → source_channel      (Catalog→direct, Offer→concierge)

Alsabini take: the API has no explicit field for it. Empirically verified
against the Sales 2026 sheet (82/83 exact matches):
    alsabini_take = ALSABINI_TAKE_RATE × (totalPaid − serviceFees)
        when providerCompanyName is ALSABINI S.A and createdAt >= 2026-01-01
The 5% rate is configurable via env ALSABINI_TAKE_RATE. ⚠ Confirm the rate
with the BookinGuru dev team if it ever changes.
"""

import os
import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from .sheets_sync import (
    _fetch_csv, _to_date, _new_weekly_accum, _build_weekly_records,
    _process_room_rows, fetch_hotel_aliases, _canon,
    VERTICAL_MAP, SOURCE_CHANNEL, HOTEL_ROOM_GID, HOTEL_ROOM_TAB, HOTEL_ALIAS_GID,
)

REPORTS_URL = os.getenv(
    "BOOKINGURU_REPORTS_URL",
    "https://app.bookinguru.com/api/reports/bookings",
)
PAGE_LIMIT = 1000          # API max rows per page
MAX_RETRIES = 3

# Alsabini margin rule (see module docstring). Applied from 2026 onward to
# mirror the sheet era, where the "Alsabini take" column only existed on the
# Sales 2026 tab.
ALSABINI_TAKE_RATE = float(os.getenv("ALSABINI_TAKE_RATE", "0.05"))
ALSABINI_TAKE_SINCE = date(2026, 1, 1)


def is_configured() -> bool:
    """API mode is active when the reports API key is present."""
    return bool(os.getenv("BOOKINGURU_REPORTS_API_KEY"))


# ── Fetch ────────────────────────────────────────────────────────────────────

def _get_page(page: int, date_from: Optional[date], date_to: Optional[date]) -> dict:
    params = {"page": page, "limit": PAGE_LIMIT}
    if date_from: params["from"] = date_from.isoformat()
    if date_to:   params["to"] = date_to.isoformat()
    url = f"{REPORTS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "x-api-key": os.environ["BOOKINGURU_REPORTS_API_KEY"],
        "User-Agent": "BookinGuru-Dashboard-Sync/1.0",
    })
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401):   # client errors — don't retry
                raise
            last_exc = exc
        except Exception as exc:         # network / 5xx / timeout
            last_exc = exc
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Reports API page {page} failed after {MAX_RETRIES} tries: {last_exc}")


def fetch_report_rows(date_from: Optional[date] = None,
                      date_to: Optional[date] = None) -> List[dict]:
    """Fetch ALL bookings from the reports API (paginated), deduped by ref."""
    first = _get_page(1, date_from, date_to)
    rows = list(first.get("data", []))
    total = int(first.get("total", len(rows)))
    page = 1
    while page * PAGE_LIMIT < total:
        page += 1
        rows.extend(_get_page(page, date_from, date_to).get("data", []))
    # Dedupe by referenceNumber (data can shift between page fetches)
    seen: dict = {}
    for r in rows:
        ref = (r.get("referenceNumber") or "").strip()
        if ref:
            seen[ref] = r
    return list(seen.values())


# ── Conversion ───────────────────────────────────────────────────────────────

def _money(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace("€", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_offered_commission(v) -> Tuple[Optional[float], Optional[float]]:
    """'12.00 €' → (12.0, None) · '15 %' → (None, 15.0) · null → (None, None)."""
    if not v:
        return None, None
    s = str(v).strip()
    num = s.replace("€", "").replace("%", "").replace(",", "").strip()
    try:
        val = float(num)
    except ValueError:
        return None, None
    if "%" in s:
        return None, val
    return val, None


def _alsabini_take(provider: str, reservation_date: date, total_paid: float,
                   service_fees: float) -> float:
    if reservation_date < ALSABINI_TAKE_SINCE:
        return 0.0
    if not (provider or "").strip().upper().startswith("ALSABINI"):
        return 0.0
    take = ALSABINI_TAKE_RATE * (total_paid - service_fees)
    return round(take, 2) if take > 0 else 0.0


def convert_rows(rows: List[dict], alias_map: Dict[str, str],
                 errors: List[str]) -> List[dict]:
    """API rows → daily-record dicts (same shape the sheet parser produced)."""
    records: List[dict] = []
    skipped_no_hotel = 0
    skipped_bad = 0
    for r in rows:
        ref = (r.get("referenceNumber") or "").strip()
        if not ref:
            skipped_bad += 1
            continue
        hotel = _canon((r.get("conciergeCompanyName") or "").strip(), alias_map)
        if not hotel:
            # Same rule as the sheet era: bookings without a hotel are excluded
            # from the dashboard (they'd distort per-hotel + portfolio totals).
            skipped_no_hotel += 1
            continue
        reservation_date = _to_date(r.get("createdAt") or "")
        if reservation_date is None:
            skipped_bad += 1
            continue

        total_paid   = _money(r.get("totalPaid"))
        service_fees = _money(r.get("serviceFees"))
        provider     = (r.get("providerCompanyName") or "").strip() or None
        comm_eur, comm_pct = _parse_offered_commission(r.get("offeredCommission"))
        raw_source = (r.get("source") or "").lower().strip()

        records.append({
            "booking_ref":             ref,
            "hotel_name_raw":          hotel,
            "reservation_date":        reservation_date,
            "vertical_name":           (r.get("vertical") or "").strip() or None,
            "product_name":            (r.get("productName") or "").strip() or None,
            "product_option":          (r.get("variantName") or "").strip() or None,
            "service_date":            _to_date(r.get("startDateAndTime") or ""),
            "payment_method":          (r.get("paymentMethod") or "").strip() or None,
            "total_paid":              total_paid,
            "service_fees":            service_fees,
            "alsabini_take":           _alsabini_take(provider or "", reservation_date,
                                                      total_paid, service_fees),
            "reservation_status":      (r.get("status") or "").strip() or None,
            "payment_status":          (r.get("paymentStatus") or "").strip() or None,
            "provider_payout":         _money(r.get("providerPayout")) or None,
            "offered_commission_eur":  comm_eur,
            "offered_commission_pct":  comm_pct,
            "company_name":            provider,
            "source_channel":          SOURCE_CHANNEL.get(raw_source),
            "data_year":               reservation_date.year,
        })
    if skipped_no_hotel:
        errors.append(f"[Reports API] skipped {skipped_no_hotel} booking(s) with no hotel "
                      f"(conciergeCompanyName empty)")
    if skipped_bad:
        errors.append(f"[Reports API] skipped {skipped_bad} row(s) missing ref/date")
    return records


def build_weekly_records(daily_records: List[dict], errors: List[str]) -> List[dict]:
    """
    Aggregate daily records into weekly per-hotel records using the SAME rules
    as the old sheet parser (_process_sheet), so all dashboard KPIs stay
    consistent: Cancelled rows tracked but excluded from money, commission =
    service fees + Alsabini take, category/vertical/channel/segment splits.
    """
    data: Dict = defaultdict(lambda: defaultdict(_new_weekly_accum))
    for rec in daily_records:
        rd: date = rec["reservation_date"]
        week = rd - timedelta(days=rd.weekday())
        entry = data[rec["hotel_name_raw"]][week]

        status = rec["reservation_status"] or ""
        entry["has_status_tracking"] = True
        if status == "Completed":
            entry["completed"] += 1
        elif status == "Cancelled":
            entry["cancelled"] += 1
        if status == "Cancelled":
            continue

        gmv         = rec["total_paid"]
        service_fee = rec["service_fees"]
        take        = rec["alsabini_take"]
        commission  = service_fee + take

        vertical = (rec["vertical_name"] or "other").lower().strip() or "other"
        category = VERTICAL_MAP.get(vertical, "other")

        entry["gmv"] += gmv
        entry["transactions"] += 1
        entry["commission"] += commission
        entry["cat"][category] += gmv
        entry["vert"][vertical]["gmv"] += gmv
        entry["vert"][vertical]["rev"] += commission

        channel = rec["source_channel"]
        if channel == "direct":
            entry["direct_gmv"] += gmv
            entry["direct_rev"] += commission
        elif channel == "concierge":
            entry["concierge_gmv"] += gmv
            entry["concierge_rev"] += commission

        entry["bg_general_rev"] += service_fee
        if take > 0:
            entry["alsabini_gmv"] += gmv
            entry["alsabini_rev"] += take
        else:
            entry["bg_general_gmv"] += gmv

    return _build_weekly_records(data, errors)


# ── Top-level: everything the sync needs, fetched concurrently ───────────────

def sync_all_parallel_api() -> Tuple[List[dict], List[dict], List[dict],
                                     Dict[str, str], List[str]]:
    """
    API-mode replacement for sheets_sync.sync_all_parallel().
    Bookings come from the Reports API; Rooms + Hotel Aliases still come from
    the Google Sheet. Returns the same shape:
        (weekly_records, daily_records, room_records, alias_map, errors)
    """
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_api   = pool.submit(fetch_report_rows)
        f_rooms = pool.submit(_fetch_csv, gid=HOTEL_ROOM_GID)
        f_alias = pool.submit(fetch_hotel_aliases)

        try:
            alias_map = f_alias.result()
        except Exception as exc:
            errors.append(f"Hotel Aliases tab (gid {HOTEL_ALIAS_GID}) fetch failed: {exc}")
            alias_map = {}

        try:
            api_rows = f_api.result()
        except Exception as exc:
            errors.append(f"Reports API fetch failed: {exc}")
            api_rows = []

        try:
            room_rows = f_rooms.result()
        except Exception as exc:
            errors.append(f"Rooms tab (gid {HOTEL_ROOM_GID}) fetch failed: {exc}")
            room_rows = []

    daily = convert_rows(api_rows, alias_map, errors)
    weekly = build_weekly_records(daily, errors)

    room_records, room_errs = _process_room_rows(room_rows)
    errors.extend(room_errs)

    print(f"DIAGNOSTIC — Reports API sync: {len(api_rows)} bookings fetched, "
          f"{len(daily)} daily records, {len(weekly)} weekly hotel-week records")
    return weekly, daily, room_records, alias_map, errors
