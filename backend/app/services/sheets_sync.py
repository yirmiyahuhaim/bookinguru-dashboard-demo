"""
sheets_sync.py
──────────────
Reads Sales 2025 and Sales 2026 tabs from a Google Sheet (set via the
GOOGLE_SHEET_ID env var), aggregates per hotel per week, and returns records
compatible with the DB upsert in upload.py.

Authentication
──────────────
Two modes are supported automatically:

1. Public sheet ("Anyone with the link" access)
   No configuration needed — the CSV export URL works without credentials.

2. Restricted sheet (only specific Google accounts have access)
   Set the env var GOOGLE_SERVICE_ACCOUNT_JSON to the full JSON content of a
   Google service account key file. Then add the service account's client_email
   as a Viewer on the Google Sheet. The backend will obtain a short-lived access
   token and attach it to every request.

   Steps to set up:
   a) Google Cloud Console → IAM → Service Accounts → Create service account
   b) Keys tab → Add key → JSON → download the file
   c) Copy the entire JSON content into a Render env var called
      GOOGLE_SERVICE_ACCOUNT_JSON (paste as one line or multi-line — both work)
   d) In Google Sheets → Share → add the service account email (client_email
      from the JSON) as Viewer
"""

import csv
import io
import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

SHEET_ID        = os.getenv("GOOGLE_SHEET_ID", "")
HOTEL_ROOM_TAB      = "Hotel Room number"   # kept for error messages only — fetched by GID below
HOTEL_ROOM_GID      = "475828665"           # "Rooms" tab
FORECAST_TAB_GID    = "748583968"           # "Forecast" tab
HOTEL_ALIAS_GID     = "70220029"            # "Hotel Aliases" tab (col A = main name, col B+ = aliases)


def fetch_hotel_aliases() -> Dict[str, str]:
    """
    Fetch the Hotel Aliases tab → {alias_lowercased: canonical_main_name}.
    Col A is the main/first name; every other column on the row is an alias
    that should be folded into it. Returns {} on any fetch error (never fatal).
    """
    try:
        rows = _fetch_csv(gid=HOTEL_ALIAS_GID)
    except Exception:
        return {}
    amap: Dict[str, str] = {}
    for row in rows[1:]:                      # skip header
        if not row:
            continue
        main = row[0].strip()
        if not main:
            continue
        for alias in row[1:]:
            a = alias.strip()
            if a and a.lower() != main.lower():
                amap[a.lower()] = main
    return amap


def _canon(name: str, alias_map: Optional[Dict[str, str]]) -> str:
    """Rewrite an alias hotel name to its canonical main name (case-insensitive)."""
    if not alias_map or not name:
        return name
    return alias_map.get(name.strip().lower(), name)

VERTICAL_MAP = {
    "cars":           "cars",
    "transportation": "transfers",
    "airportshuttle": "transfers",
    "cruises":        "experiences",
    "outdoors":       "experiences",
    "tours":          "experiences",
    "nightlife":      "experiences",
    "vessels":        "experiences",
    "food":           "experiences",
    "wellness":       "wellness",
    "other":          "other",
}


# Token cache — avoids re-fetching the OAuth token on every sync
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _service_account_token() -> Optional[str]:
    """
    Return a cached OAuth2 Bearer token. Tokens last 60 min; cache TTL is 50 min.
    Returns None in public-sheet mode (no GOOGLE_SERVICE_ACCOUNT_JSON set).
    """
    global _token_cache
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        return None
    try:
        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore

        info = json.loads(creds_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        creds.refresh(Request())
        _token_cache = {"token": creds.token, "expires_at": now + 3000}  # 50 min TTL
        return creds.token  # type: ignore[return-value]
    except Exception as exc:
        raise RuntimeError(f"Failed to obtain service-account token: {exc}") from exc


def _fetch_csv(sheet_name: Optional[str] = None, *, gid: Optional[str] = None) -> List[List[str]]:
    """
    Download a single sheet tab as CSV.

    Uses /export?format=csv for both authenticated and public sheets — this
    endpoint is significantly faster than the /gviz/tq alternative.
    """
    if sheet_name is None and gid is None:
        raise ValueError("Provide either sheet_name or gid")

    # Token is cached after first call — safe to call from multiple threads
    token = _service_account_token()

    if gid is not None:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    else:
        encoded = urllib.parse.quote(sheet_name)  # type: ignore[arg-type]
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet={encoded}"

    headers = {"User-Agent": "BookinGuru-Sync/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    label = gid if gid else sheet_name
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8-sig")

    if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):
        raise RuntimeError(
            f"Google returned an HTML page for sheet '{label}'. "
            "The sheet may be restricted — set GOOGLE_SERVICE_ACCOUNT_JSON in Render env vars."
        )

    return list(csv.reader(io.StringIO(text)))


def _to_date(val: str) -> Optional[date]:
    """Parse a date or datetime string to an exact date (NOT rounded to Monday)."""
    if not val:
        return None
    val = val.strip()
    # Try datetime formats first (handles both zero-padded and single-digit hours)
    # e.g. "2025-03-14 00:00:00", "2025-04-30 2:10:08", "2025-03-14T08:30:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val[:19], fmt).date()
        except ValueError:
            continue
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _week_monday(val: str) -> date:
    # Reuse the robust parser (_to_date handles datetimes with single-digit
    # hours like "2025-04-30 2:10:08", which strptime/fromisoformat-by-hand
    # would otherwise reject and silently drop).
    d = _to_date(val)
    if d is None:
        raise ValueError(f"Cannot parse date: {val!r}")
    return d - timedelta(days=d.weekday())


def _to_float(val: str) -> float:
    if not val or val.strip() == "":
        return 0.0
    try:
        return float(val.strip().replace("%", "").replace("€", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


SOURCE_CHANNEL = {
    "catalog":   "direct",
    "catalogue": "direct",
    "offer":     "concierge",
}


def _process_sheet(
    rows: List[List[str]],
    *,
    hotel_col: int,
    status_col: int,
    date_col: int,
    gmv_col: int,
    commission_col: int,
    commission_col2: Optional[int],
    vertical_col: int,
    source_col: int,
    source_col2: Optional[int],
    track_cancellations: bool,
    label: str,
    data: Dict,
    errors: List[str],
    alias_map: Optional[Dict[str, str]] = None,
) -> None:
    min_cols = max(hotel_col, status_col, date_col, gmv_col, commission_col, vertical_col, source_col) + 1

    # Skip-reason counters — surfaced as a summary at the end so silently-dropped
    # rows (e.g. a real booking missing its hotel name) become visible.
    skip = {"short": 0, "blank_hotel": 0, "blank_status": 0, "bad_date": 0}
    LOG_CAP = 8  # cap noisy per-row logs; the summary carries the full counts

    def _maybe_log(msg: str, kind: str):
        if skip[kind] <= LOG_CAP:
            errors.append(msg)

    for i, row in enumerate(rows[1:], start=2):
        # Does this row carry real data? (used to tell a genuine row apart from
        # empty trailing padding when a key cell is blank)
        _has_data = (
            (len(row) > date_col and row[date_col].strip())
            or (len(row) > gmv_col and row[gmv_col].strip())
        )

        if len(row) < min_cols:
            if _has_data:
                skip["short"] += 1
                _maybe_log(f"[{label}] row {i}: only {len(row)} cols (need {min_cols}), skipped", "short")
            continue
        raw_hotel = row[hotel_col].strip()
        if not raw_hotel:
            # A row with a date/amount but no hotel name is a real row dropped
            # silently — count it so it shows up in the sync summary.
            if _has_data:
                skip["blank_hotel"] += 1
                _maybe_log(f"[{label}] row {i}: has data but blank hotel name (col {hotel_col + 1}), skipped", "blank_hotel")
            continue  # genuinely empty padding rows are ignored
        # Skip total/subtotal rows: their "hotel" cell contains a monetary value or bare number
        _h_clean = raw_hotel.lstrip("€").replace(",", "").replace(".", "").replace(" ", "")
        if raw_hotel.startswith("€") or _h_clean.lstrip("-").isdigit():
            continue  # silently skip — these are sheet total rows
        status = row[status_col].strip()
        if not status:
            skip["blank_status"] += 1
            _maybe_log(f"[{label}] row {i}: hotel '{raw_hotel}' has no status, skipped", "blank_status")
            continue

        try:
            week = _week_monday(row[date_col])
        except ValueError as exc:
            skip["bad_date"] += 1
            _maybe_log(f"[{label}] row {i}: {exc}", "bad_date")
            continue

        raw_hotel = _canon(raw_hotel, alias_map)   # fold alias names into the main hotel
        entry = data[raw_hotel][week]

        if track_cancellations:
            entry["has_status_tracking"] = True
            if status == "Completed":
                entry["completed"] += 1
            elif status == "Cancelled":
                entry["cancelled"] += 1

        if status == "Cancelled":
            continue

        gmv          = _to_float(row[gmv_col])
        service_fee  = _to_float(row[commission_col])                            # col I always
        alsabini_take = (
            _to_float(row[commission_col2])
            if commission_col2 is not None and len(row) > commission_col2
            else 0.0
        )                                                                         # col K, 2026 only
        commission = service_fee + alsabini_take

        vertical = row[vertical_col].lower().strip() if row[vertical_col] else "other"
        category = VERTICAL_MAP.get(vertical, "other")

        # Check primary source col first, fall back to secondary (col AB for 2026
        # which carries the clean Offer/Catalog label when col S has an IBAN).
        raw_source = ""
        if source_col2 is not None and len(row) > source_col2 and row[source_col2]:
            raw_source = str(row[source_col2]).lower().strip()
        if not raw_source and len(row) > source_col and row[source_col]:
            raw_source = str(row[source_col]).lower().strip()
        channel = SOURCE_CHANNEL.get(raw_source)  # "direct", "concierge", or None

        entry["gmv"]           += gmv
        entry["transactions"]  += 1
        entry["commission"]    += commission
        entry["cat"][category] += gmv
        # Raw vertical tracking (uses the actual column C value, not the mapped category)
        entry["vert"][vertical]["gmv"] += gmv
        entry["vert"][vertical]["rev"] += commission

        # Purchase channel (Catalog / Offer)
        if channel == "direct":
            entry["direct_gmv"]     += gmv
            entry["direct_rev"]     += commission
        elif channel == "concierge":
            entry["concierge_gmv"]  += gmv
            entry["concierge_rev"]  += commission

        # Revenue segment (BG General = col I, Alsabini = col K)
        # BG General Revenue = service fee on ALL rows (Alsabini + non-Alsabini)
        entry["bg_general_rev"] += service_fee
        if alsabini_take > 0:
            entry["alsabini_gmv"] += gmv
            entry["alsabini_rev"] += alsabini_take
        else:
            entry["bg_general_gmv"] += gmv

    # ── Skip summary — makes silently-dropped rows visible in the sync result ──
    total_skipped = sum(skip.values())
    if total_skipped:
        bits = []
        if skip["blank_hotel"]:  bits.append(f"{skip['blank_hotel']} blank hotel name (col {hotel_col + 1})")
        if skip["blank_status"]: bits.append(f"{skip['blank_status']} blank status")
        if skip["short"]:        bits.append(f"{skip['short']} too few columns")
        if skip["bad_date"]:     bits.append(f"{skip['bad_date']} unparseable date")
        errors.append(f"[{label}] skipped {total_skipped} data row(s): " + ", ".join(bits))


def _new_weekly_accum() -> dict:
    return {
        "gmv": 0.0, "transactions": 0, "commission": 0.0,
        "cat": defaultdict(float),
        "completed": 0, "cancelled": 0, "has_status_tracking": False,
        "direct_gmv": 0.0, "direct_rev": 0.0,
        "concierge_gmv": 0.0, "concierge_rev": 0.0,
        "bg_general_gmv": 0.0, "bg_general_rev": 0.0,
        "alsabini_gmv": 0.0, "alsabini_rev": 0.0,
        "vert": defaultdict(lambda: {"gmv": 0.0, "rev": 0.0}),
    }


def _build_weekly_records(data: Dict, errors: List[str]) -> List[dict]:
    """Convert the per-(hotel, week) accumulator dict into flat record dicts."""
    records: List[dict] = []
    for hotel_name, weeks in data.items():
        for week, e in weeks.items():
            txns       = e["transactions"]
            gmv        = round(e["gmv"], 2)
            commission = e["commission"]
            take_rate  = round(commission / gmv * 100, 4) if gmv else 0.0
            bg_rev     = round(commission, 2)
            aov        = round(gmv / txns, 2) if txns > 0 else 0.0

            def _cat(key: str) -> Optional[float]:
                v = e["cat"].get(key, 0.0)
                return round(v, 2) if v > 0 else None

            def _channel(key: str) -> Optional[float]:
                v = e[key]
                return round(v, 2) if v > 0 else None

            canc_rate: Optional[float] = None
            canc_count: Optional[int] = None
            if e["has_status_tracking"]:
                total = e["completed"] + e["cancelled"]
                canc_rate = round(e["cancelled"] / total * 100, 2) if total > 0 else 0.0
                canc_count = e["cancelled"]

            records.append({
                "hotel_name":          hotel_name,
                "week_start_date":     week,
                "gmv":                 gmv,
                "transactions":        txns,
                "take_rate":           take_rate,
                "bg_gross_revenue":    bg_rev,
                "avg_cart_value":      aov,
                "cars_gmv":            _cat("cars"),
                "transfers_gmv":       _cat("transfers"),
                "experiences_gmv":     _cat("experiences"),
                "wellness_gmv":        _cat("wellness"),
                "other_gmv":           _cat("other"),
                "cancellation_rate":   canc_rate,
                "cancelled_transactions": canc_count,
                "direct_gmv":          _channel("direct_gmv"),
                "direct_revenue":      _channel("direct_rev"),
                "concierge_gmv":       _channel("concierge_gmv"),
                "concierge_revenue":   _channel("concierge_rev"),
                "bg_general_gmv":      _channel("bg_general_gmv"),
                "bg_general_revenue":  _channel("bg_general_rev"),
                "alsabini_gmv":        _channel("alsabini_gmv"),
                "alsabini_revenue":    _channel("alsabini_rev"),
                "vertical_breakdown":  json.dumps({
                    k: {"gmv": round(v["gmv"], 2), "revenue": round(v["rev"], 2)}
                    for k, v in e["vert"].items() if v["gmv"] > 0
                }) if e["vert"] else None,
            })

    # Diagnostic commission totals — printed to server log only, not surfaced to the user
    t25 = sum(e["commission"] for h, ws in data.items() for w, e in ws.items() if w.year == 2025)
    t26 = sum(e["commission"] for h, ws in data.items() for w, e in ws.items() if w.year == 2026)
    print(f"DIAGNOSTIC — raw commission totals: 2025=€{t25:.2f}, 2026=€{t26:.2f}, combined=€{t25+t26:.2f}")
    return records


# Tab-level config for processing — one entry per Sales year tab
_SHEET_TABS = [
    {
        "name": "Sales 2025",
        "gid": "565328354",   # fetched by GID — immune to tab rename
        # Weekly aggregation params
        "weekly": dict(
            hotel_col=16, status_col=9, date_col=0,
            gmv_col=7, commission_col=8, commission_col2=None,
            vertical_col=2, source_col=17, source_col2=None,
            track_cancellations=False,
        ),
        # Daily parsing params
        "daily": dict(
            hotel_col=16, status_col=9, commission_col2=None,
            vendor_col=None, source_col=17, source_col2=None,
            data_year=2025,
        ),
    },
    {
        "name": "Sales 2026",
        "gid": "707903923",   # fetched by GID — immune to tab rename
        "weekly": dict(
            hotel_col=22, status_col=11, date_col=0,
            gmv_col=7, commission_col=8, commission_col2=10,
            vertical_col=2, source_col=18, source_col2=27,
            track_cancellations=True,
        ),
        "daily": dict(
            hotel_col=22, status_col=11, commission_col2=10,
            vendor_col=16, source_col=18, source_col2=27,
            data_year=2026,
        ),
    },
]


def sync_all_from_sheets() -> Tuple[List[dict], List[dict], List[str]]:
    """
    Fetch each Sales tab ONCE and return both weekly-aggregated records and
    individual daily booking records in a single pass.

    Returns (weekly_records, daily_records, errors).
    This halves the number of HTTP requests vs calling the two older functions
    separately.
    """
    data: Dict = defaultdict(lambda: defaultdict(_new_weekly_accum))
    daily: List[dict] = []
    errors: List[str] = []

    for tab in _SHEET_TABS:
        try:
            rows = _fetch_csv(gid=tab["gid"])   # by GID — immune to tab rename
            _process_sheet(rows, label=tab["name"], data=data, errors=errors, **tab["weekly"])
            _parse_daily_sheet(rows, label=tab["name"], records=daily, errors=errors, **tab["daily"])
        except Exception as exc:
            errors.append(f"{tab['name']} fetch failed: {exc}")

    weekly = _build_weekly_records(data, errors)
    return weekly, daily, errors


def aggregate_from_sheets() -> Tuple[List[dict], List[str]]:
    """
    Backward-compatible wrapper — returns only the weekly records.
    Prefer sync_all_from_sheets() when you also need daily data.
    """
    weekly, _daily, errors = sync_all_from_sheets()
    return weekly, errors


# ── Hotel room-count sync ────────────────────────────────────────────────────

_ROOM_JUNK = frozenset({"-", "", "nan", "none", "ibiza", "provider",
                        "sant antonio", "santa eulalia"})


def _process_room_rows(rows: List[List[str]]) -> Tuple[List[dict], List[str]]:
    """Parse already-fetched rows from the Hotel Room Number tab."""
    if not rows:
        return [], [f"'{HOTEL_ROOM_TAB}' tab returned no data"]

    # Find header row — first row that contains a cell with any room-related keyword
    _ROOM_KEYWORDS = ("rooms", "room", "habitacion", "habitación", "hab.", "cuartos", "nro")
    header_row_idx: Optional[int] = None
    for i, row in enumerate(rows[:10]):   # search within first 10 rows
        if any(any(kw in str(c).lower() for kw in _ROOM_KEYWORDS) for c in row):
            header_row_idx = i
            break

    if header_row_idx is None:
        # Surface the actual cell values from the first 3 rows to aid debugging
        sample = "; ".join(
            " | ".join(str(c).strip() for c in row[:10])
            for row in rows[:3]
        )
        return [], [
            f"'{HOTEL_ROOM_TAB}' tab: could not find a 'Rooms' column header. "
            f"First 3 rows (cols A–J): {sample}"
        ]

    headers   = [str(c).lower().strip() for c in rows[header_row_idx]]
    data_rows = rows[header_row_idx + 1:]

    def _col(*candidates: str) -> Optional[int]:
        for cand in candidates:
            for i, h in enumerate(headers):
                if cand in h:
                    return i
        return None

    rooms_idx    = _col("rooms", "room", "habitacion", "habitación", "hab.", "cuartos", "nro")
    category_idx = _col("category", "categoria", "type", "tipo")
    real_idx     = _col("nombre real", "real name", "nombre_real")
    client_idx   = _col("cliente", "client", "hotel", "name")

    if rooms_idx is None:
        return [], [f"'{HOTEL_ROOM_TAB}' tab: no 'Rooms' column detected after parsing headers"]

    records: List[dict] = []
    for row in data_rows:
        # Skip short rows or rows without a rooms value
        if len(row) <= rooms_idx:
            continue
        raw_rooms = str(row[rooms_idx]).strip().replace(",", "")
        try:
            rooms = int(float(raw_rooms))
        except (ValueError, TypeError):
            continue
        if rooms <= 0:
            continue

        # Collect hotel names (prefer NOMBRE REAL, fall back to Cliente)
        names: List[str] = []
        for idx in [real_idx, client_idx]:
            if idx is not None and len(row) > idx:
                n = str(row[idx]).strip()
                if n.lower() not in _ROOM_JUNK:
                    names.append(n)
        if not names:
            continue

        # Property type / category
        property_type: Optional[str] = None
        if category_idx is not None and len(row) > category_idx:
            cat = str(row[category_idx]).strip()
            if cat.lower() not in _ROOM_JUNK:
                property_type = cat

        records.append({"names": names, "rooms": rooms, "property_type": property_type})

    return records, []


def sync_room_counts_from_sheets() -> Tuple[List[dict], List[str]]:
    """Fetch the Rooms tab (by GID) and return room-count records."""
    try:
        rows = _fetch_csv(gid=HOTEL_ROOM_GID)
    except Exception as exc:
        return [], [f"'{HOTEL_ROOM_TAB}' tab fetch failed: {exc}"]
    return _process_room_rows(rows)


# ── Parallel all-tabs fetch ──────────────────────────────────────────────────

def sync_all_parallel() -> Tuple[List[dict], List[dict], List[dict], Dict[str, str], List[str]]:
    """
    Fetch the Google Sheet tabs concurrently (Sales 2025, Sales 2026,
    Hotel Room Number, Hotel Aliases) to cut HTTP time.

    Returns (weekly_records, daily_records, room_records, alias_map, errors).
    Hotels are derived from the Sales tabs; alias names are folded into their
    canonical main hotel during parsing.
    """
    raw: Dict[str, List[List[str]]] = {}
    errors: List[str] = []

    # Pre-warm token cache before spawning threads — avoids N simultaneous auth requests
    try:
        _service_account_token()
    except Exception as exc:
        errors.append(f"Auth token fetch failed: {exc}")

    # All tabs fetched by GID (reliable, immune to tab rename — name-based fetch
    # silently returns the wrong tab when the name doesn't match exactly).
    with ThreadPoolExecutor(max_workers=len(_SHEET_TABS) + 2) as pool:
        f_sales = {pool.submit(_fetch_csv, gid=t["gid"]): t["name"] for t in _SHEET_TABS}
        f_rooms = pool.submit(_fetch_csv, gid=HOTEL_ROOM_GID)
        f_alias = pool.submit(fetch_hotel_aliases)

        for future, name in f_sales.items():
            try:
                raw[name] = future.result()
            except Exception as exc:
                errors.append(f"{name} fetch failed: {exc}")
                raw[name] = []

        try:
            raw[HOTEL_ROOM_TAB] = f_rooms.result()
        except Exception as exc:
            errors.append(f"Rooms tab (gid {HOTEL_ROOM_GID}) fetch failed: {exc}")
            raw[HOTEL_ROOM_TAB] = []

        try:
            alias_map = f_alias.result()
        except Exception as exc:
            errors.append(f"Hotel Aliases tab (gid {HOTEL_ALIAS_GID}) fetch failed: {exc}")
            alias_map = {}

    # Process Sales tabs sequentially (order matters for data accumulation)
    data: Dict = defaultdict(lambda: defaultdict(_new_weekly_accum))
    daily: List[dict] = []
    for tab in _SHEET_TABS:
        rows = raw.get(tab["name"], [])
        if rows:
            try:
                _process_sheet(rows, label=tab["name"], data=data, errors=errors, alias_map=alias_map, **tab["weekly"])
                _parse_daily_sheet(rows, label=tab["name"], records=daily, errors=errors, alias_map=alias_map, **tab["daily"])
            except Exception as exc:
                errors.append(f"{tab['name']} process failed: {exc}")

    weekly = _build_weekly_records(data, errors)

    room_records, room_errs = _process_room_rows(raw.get(HOTEL_ROOM_TAB, []))
    errors.extend(room_errs)

    return weekly, daily, room_records, alias_map, errors


# ── Daily booking ingestion ──────────────────────────────────────────────────

def _parse_daily_sheet(
    rows: List[List[str]],
    *,
    hotel_col: int,
    status_col: int,
    commission_col2: Optional[int],   # Alsabini take column (None for 2025)
    vendor_col: Optional[int],         # Vendor/company column (None for 2025)
    source_col: int,
    source_col2: Optional[int],        # Secondary source column (col AB in 2026)
    data_year: int,
    label: str,
    records: List[dict],
    errors: List[str],
    alias_map: Optional[Dict[str, str]] = None,
) -> None:
    """
    Parse individual booking rows from a Sales tab into flat dicts.
    Appends to `records` in-place.

    Column layout (shared across both years unless overridden by params):
      0  Reservation date and time
      1  Booking Ref
      2  Vertical Name
      3  Product Name
      4  Product option
      5  Service Date and Time
      6  Payment method
      7  Total Paid (€)
      8  Service Fees (€)
     12  Payment Status          (2026 col 12; 2025 ~col 10 — stored as-is)
     13  Provider's payout (€)   (2026 col 13)
     14  Offered Commission (€)  (2026 col 14)
     15  Offered Commission %    (2026 col 15)
    """

    def _cell(row: List[str], idx: Optional[int], default: str = "") -> str:
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip()

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 9:
            continue

        booking_ref = _cell(row, 1)
        # Skip rows without a valid booking reference
        if not booking_ref or not booking_ref.startswith("BK-"):
            continue

        hotel_name = _cell(row, hotel_col)
        if not hotel_name:
            continue
        hotel_name = _canon(hotel_name, alias_map)   # fold alias names into the main hotel

        raw_date = _cell(row, 0)
        reservation_date = _to_date(raw_date)
        if reservation_date is None:
            errors.append(f"[{label}] row {i}: cannot parse date '{raw_date}', skipped")
            continue

        service_date = _to_date(_cell(row, 5))
        reservation_status = _cell(row, status_col) or None

        # Source channel — prefer secondary col (col AB in 2026) then primary
        raw_source = _cell(row, source_col2) if source_col2 else ""
        if not raw_source:
            raw_source = _cell(row, source_col)
        source_channel = SOURCE_CHANNEL.get(raw_source.lower()) if raw_source else None

        records.append({
            "booking_ref":             booking_ref,
            "hotel_name_raw":          hotel_name,
            "reservation_date":        reservation_date,
            "vertical_name":           _cell(row, 2) or None,
            "product_name":            _cell(row, 3) or None,
            "product_option":          _cell(row, 4) or None,
            "service_date":            service_date,
            "payment_method":          _cell(row, 6) or None,
            "total_paid":              _to_float(_cell(row, 7)),
            "service_fees":            _to_float(_cell(row, 8)),
            "alsabini_take":           _to_float(_cell(row, commission_col2)) if commission_col2 else 0.0,
            "reservation_status":      reservation_status,
            "payment_status":          _cell(row, 12) or None,
            "provider_payout":         _to_float(_cell(row, 13)) or None,
            "offered_commission_eur":  _to_float(_cell(row, 14)) or None,
            "offered_commission_pct":  _to_float(_cell(row, 15)) or None,
            "company_name":            _cell(row, vendor_col) or None,
            "source_channel":          source_channel,
            "data_year":               data_year,
        })



def parse_daily_from_sheets() -> Tuple[List[dict], List[str]]:
    """
    Backward-compatible wrapper — returns only the daily records.
    Prefer sync_all_from_sheets() to avoid fetching the sheets twice.
    """
    _weekly, daily, errors = sync_all_from_sheets()
    return daily, errors


# ── Forecast tab ─────────────────────────────────────────────────────────────

def fetch_forecast_data() -> dict:
    """
    Fetch the Forecast tab (gid 748583968) and return structured weekly data.

    Sheet layout (horizontal — first column is row label, rest are weeks):
      Row 1 (idx 0): Week labels (header)
      Row 2 (idx 1): Bookings Forecast
      Row 3 (idx 2): Bookings Actual
      Row 4 (idx 3): Bookings % off/exceeded
      Row 5 (idx 4): blank separator
      Row 6 (idx 5): GMV Forecast
      Row 7 (idx 6): GMV Actual
      Row 8 (idx 7): GMV % off/exceeded

    Returns:
      {
        "bookings": [{"week": str, "forecast": float, "actual": float|None, "pct_diff": float|None}, ...],
        "gmv":      [...same shape...],
      }
    Only weeks that have a non-blank forecast value are included.
    """
    try:
        rows = _fetch_csv(gid=FORECAST_TAB_GID)
    except Exception as exc:
        raise RuntimeError(f"Forecast tab fetch failed: {exc}") from exc

    if not rows or len(rows) < 4:
        return {"bookings": [], "gmv": []}

    # Header row: col 0 = row label (ignored), col 1+ = week labels
    week_labels: List[str] = [c.strip() for c in rows[0][1:]]

    def row_vals(idx: int) -> List[str]:
        if idx >= len(rows):
            return []
        return [c.strip() for c in rows[idx][1:]]  # skip label col

    def parse_num(val: str) -> Optional[float]:
        if not val:
            return None
        cleaned = val.replace("%", "").replace("€", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None

    bk_fc = row_vals(1)   # Row 2: Bookings Forecast
    bk_ac = row_vals(2)   # Row 3: Bookings Actual
    bk_pt = row_vals(3)   # Row 4: Bookings % off
    gm_fc = row_vals(5)   # Row 6: GMV Forecast
    gm_ac = row_vals(6)   # Row 7: GMV Actual
    gm_pt = row_vals(7)   # Row 8: GMV % off

    def build_series(
        fc_raw: List[str],
        ac_raw: List[str],
        pt_raw: List[str],
    ) -> List[dict]:
        result: List[dict] = []
        for i, week in enumerate(week_labels):
            if week.strip().lower() == "sum":
                continue  # ignore any "Sum"/total column from the source sheet
            fc = parse_num(fc_raw[i]) if i < len(fc_raw) else None
            if fc is None:
                continue  # skip weeks with no forecast value
            ac  = parse_num(ac_raw[i]) if i < len(ac_raw) else None
            pt  = parse_num(pt_raw[i]) if i < len(pt_raw) else None
            result.append({
                "week":     week,
                "forecast": fc,
                "actual":   ac,
                "pct_diff": pt,   # raw from sheet; negative = % off, positive = % exceeded
            })
        return result

    return {
        "bookings": build_series(bk_fc, bk_ac, bk_pt),
        "gmv":      build_series(gm_fc, gm_ac, gm_pt),
    }
