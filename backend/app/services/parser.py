import io
import csv
from datetime import date, datetime
from typing import Tuple, List, Dict, Any
import openpyxl


REQUIRED_COLUMNS = {"hotel_name", "week_start_date", "gmv", "transactions", "take_rate"}

COLUMN_ALIASES = {
    "hotel": "hotel_name",
    "property": "hotel_name",
    "week": "week_start_date",
    "week_start": "week_start_date",
    "date": "week_start_date",
    "gross_merchandise_value": "gmv",
    "total_gmv": "gmv",
    "bookings": "transactions",
    "paid_bookings": "transactions",
    "total_bookings": "transactions",
    "commission_rate": "take_rate",
    "take_rate_%": "take_rate",
    "checkins": "total_hotel_checkins",
    "total_checkins": "total_hotel_checkins",
    "cart_value": "avg_cart_value",
    "average_cart_value": "avg_cart_value",
    "aov": "avg_cart_value",
    "bg_revenue": "bg_gross_revenue",
    "gross_revenue": "bg_gross_revenue",
    "free_bookings": "free_transactions",
    "comp_transactions": "free_transactions",
    "rooms": "room_count",
    "total_rooms": "room_count",
    "number_of_rooms": "room_count",
    "incremental_rev": "incremental_revenue",
    "direct_booking_uplift_%": "direct_booking_uplift",
    "direct_uplift": "direct_booking_uplift",
    "offers": "offers_generated",
    "total_offers": "offers_generated",
    "offer_conversion": "offers_conversion",
    "offers_conversion_%": "offers_conversion",
    # Funnel / guest
    "guests": "unique_guests",
    "unique_guests": "unique_guests",
    "buying_guests": "unique_guests",
    "pre_arrival": "pre_arrival_bookings",
    "pre_arrival_bookings": "pre_arrival_bookings",
    "post_booking": "post_booking_bookings",
    "post_booking_bookings": "post_booking_bookings",
    "whatsapp": "whatsapp_bookings",
    "whatsapp_bookings": "whatsapp_bookings",
    "email_bookings": "email_bookings",
    "cancellation_rate_%": "cancellation_rate",
    "hotel_cancellation_rate": "cancellation_rate",
    # Supply quality
    "catalogue_total": "catalogue_total",
    "total_services": "catalogue_total",
    "catalogue_active": "catalogue_active",
    "active_services": "catalogue_active",
    "booking_attempts": "booking_attempts",
    "total_attempts": "booking_attempts",
    # Category mix
    "cars": "cars_gmv",
    "cars_gmv": "cars_gmv",
    "transfers": "transfers_gmv",
    "transfers_gmv": "transfers_gmv",
    "experiences": "experiences_gmv",
    "experiences_gmv": "experiences_gmv",
    "wellness": "wellness_gmv",
    "wellness_gmv": "wellness_gmv",
    "other_gmv": "other_gmv",
    # Purchase channel
    "direct_gmv": "direct_gmv",
    "direct_revenue": "direct_revenue",
    "concierge_gmv": "concierge_gmv",
    "concierge_revenue": "concierge_revenue",
    # Revenue segment
    "bg_general_gmv": "bg_general_gmv",
    "bg_general_revenue": "bg_general_revenue",
    "alsabini_gmv": "alsabini_gmv",
    "alsabini_revenue": "alsabini_revenue",
}


def _normalize_header(h: str) -> str:
    key = h.strip().lower().replace(" ", "_").replace("-", "_")
    return COLUMN_ALIASES.get(key, key)


def _parse_date(val: Any) -> date:
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {val!r}")


def _parse_float(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    s = str(val).strip().replace(",", "").replace("%", "").replace("€", "")
    return float(s)


def _parse_int(val: Any) -> int:
    return int(_parse_float(val))


def parse_xlsx(content: bytes) -> Tuple[List[Dict], List[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], ["Spreadsheet is empty"]
    headers = [_normalize_header(str(h)) if h else "" for h in rows[0]]
    return _rows_to_dicts(headers, rows[1:])


def parse_csv(content: bytes) -> Tuple[List[Dict], List[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], ["CSV is empty"]
    headers = [_normalize_header(h) for h in rows[0]]
    return _rows_to_dicts(headers, rows[1:])


def _rows_to_dicts(headers: List[str], data_rows) -> Tuple[List[Dict], List[str]]:
    records = []
    errors = []

    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return [], errors

    for i, row in enumerate(data_rows, start=2):
        row_dict = dict(zip(headers, row))
        if all(v is None or v == "" for v in row_dict.values()):
            continue
        try:
            def _opt_float(key):
                v = row_dict.get(key)
                return _parse_float(v) if v not in (None, "") else None

            def _opt_int(key):
                v = row_dict.get(key)
                return _parse_int(v) if v not in (None, "") else None

            record = {
                "hotel_name": str(row_dict.get("hotel_name", "")).strip(),
                "week_start_date": _parse_date(row_dict.get("week_start_date")),
                "gmv": _parse_float(row_dict.get("gmv", 0)),
                "transactions": _parse_int(row_dict.get("transactions", 0)),
                "free_transactions": _parse_int(row_dict.get("free_transactions", 0)),
                "room_count": _opt_int("room_count"),
                "take_rate": _parse_float(row_dict.get("take_rate", 0)),
                "avg_cart_value": _parse_float(row_dict.get("avg_cart_value", 0)),
                "bg_gross_revenue": _parse_float(row_dict.get("bg_gross_revenue", 0)),
                "total_hotel_checkins": _parse_int(row_dict.get("total_hotel_checkins", 0)),
                "incremental_revenue": _opt_float("incremental_revenue"),
                "direct_booking_uplift": _opt_float("direct_booking_uplift"),
                "offers_generated": _opt_int("offers_generated"),
                "offers_conversion": _opt_float("offers_conversion"),
                # New fields
                "unique_guests":         _opt_int("unique_guests"),
                "pre_arrival_bookings":  _opt_int("pre_arrival_bookings"),
                "post_booking_bookings": _opt_int("post_booking_bookings"),
                "whatsapp_bookings":     _opt_int("whatsapp_bookings"),
                "email_bookings":        _opt_int("email_bookings"),
                "cancellation_rate":     _opt_float("cancellation_rate"),
                "catalogue_total":       _opt_int("catalogue_total"),
                "catalogue_active":      _opt_int("catalogue_active"),
                "booking_attempts":      _opt_int("booking_attempts"),
                "cars_gmv":              _opt_float("cars_gmv"),
                "transfers_gmv":         _opt_float("transfers_gmv"),
                "experiences_gmv":       _opt_float("experiences_gmv"),
                "wellness_gmv":          _opt_float("wellness_gmv"),
                "other_gmv":             _opt_float("other_gmv"),
                "direct_gmv":            _opt_float("direct_gmv"),
                "direct_revenue":        _opt_float("direct_revenue"),
                "concierge_gmv":         _opt_float("concierge_gmv"),
                "concierge_revenue":     _opt_float("concierge_revenue"),
                "bg_general_gmv":        _opt_float("bg_general_gmv"),
                "bg_general_revenue":    _opt_float("bg_general_revenue"),
                "alsabini_gmv":          _opt_float("alsabini_gmv"),
                "alsabini_revenue":      _opt_float("alsabini_revenue"),
            }
            if not record["hotel_name"]:
                errors.append(f"Row {i}: missing hotel_name, skipped")
                continue
            # derive bg_gross_revenue if not provided
            if record["bg_gross_revenue"] == 0 and record["gmv"] and record["take_rate"]:
                record["bg_gross_revenue"] = record["gmv"] * (record["take_rate"] / 100)
            # derive avg_cart_value if not provided
            if record["avg_cart_value"] == 0 and record["transactions"] > 0:
                record["avg_cart_value"] = record["gmv"] / record["transactions"]
            records.append(record)
        except Exception as e:
            errors.append(f"Row {i}: {e}")

    return records, errors
