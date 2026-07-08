"""
Parse an ALSABINI-style hotel list Excel file and update room_count + property_type in the DB.

Expected columns (case-insensitive): Rooms, Category, Cliente, NOMBRE REAL (or similar)
Falls back to any column whose header contains "hotel" or "name".
"""
import io
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional

import openpyxl
from sqlalchemy.orm import Session

from ..models import Hotel

# Category values that are section headers / noise — not real property types
_JUNK_CATEGORIES = {"-", "ibiza", "provider", "sant antonio", "santa eulalia", "none", "nan", ""}


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _find_header_idx(headers: List[str], *candidates) -> Optional[int]:
    """Return column index of the first header that contains any candidate substring."""
    for col in candidates:
        for i, h in enumerate(headers):
            if col in h.lower():
                return i
    return None


def _try_int(val: Any) -> Optional[int]:
    try:
        v = int(float(str(val).strip().replace(",", "")))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _clean_category(val: Any) -> Optional[str]:
    """Return a clean property_type string, or None if it's noise."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in _JUNK_CATEGORIES:
        return None
    return s


def process_room_counts(content: bytes, db: Session) -> Dict:
    """
    Parse Excel, fuzzy-match hotel names against DB, update room_count and property_type.
    Returns a summary dict with updated / skipped / unmatched entries.
    """
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))

    # ── find header row (first row that contains "rooms") ─────────────────────
    header_row_idx = None
    for i, row in enumerate(all_rows):
        cleaned = [str(c).lower().strip() if c else "" for c in row]
        if "rooms" in cleaned:
            header_row_idx = i
            break

    if header_row_idx is None:
        return {"error": "Could not find a 'Rooms' column in the file.", "updated": 0,
                "updates": [], "unmatched": []}

    raw_headers = [str(c).lower().strip() if c else "" for c in all_rows[header_row_idx]]
    data_rows   = all_rows[header_row_idx + 1:]

    rooms_idx    = _find_header_idx(raw_headers, "rooms")
    category_idx = _find_header_idx(raw_headers, "category", "categoria", "type", "tipo")
    real_idx     = _find_header_idx(raw_headers, "nombre real", "real name", "nombre_real")
    client_idx   = _find_header_idx(raw_headers, "cliente", "client", "hotel", "name")

    if rooms_idx is None:
        return {"error": "No 'Rooms' column detected.", "updated": 0, "updates": [], "unmatched": []}

    # ── build Excel lookup: list of {names, rooms, property_type} ────────────
    xl_entries: List[Dict] = []
    for row in data_rows:
        rooms = _try_int(row[rooms_idx]) if len(row) > rooms_idx else None
        if rooms is None:
            continue
        names = []
        for idx in [real_idx, client_idx]:
            if idx is not None and len(row) > idx and row[idx]:
                n = str(row[idx]).strip()
                if n and n.lower() not in ("nan", "none", "-"):
                    names.append(n)
        if not names:
            continue
        category = None
        if category_idx is not None and len(row) > category_idx:
            category = _clean_category(row[category_idx])
        xl_entries.append({"names": names, "rooms": rooms, "property_type": category})

    if not xl_entries:
        return {"error": "No valid room-count rows found in file.",
                "updated": 0, "updates": [], "unmatched": []}

    # ── fuzzy-match each DB hotel to the best Excel entry ─────────────────────
    hotels = db.query(Hotel).all()
    THRESHOLD = 0.55

    updated_list   = []
    skipped_list   = []
    unmatched_list = []

    for hotel in hotels:
        best_score   = 0.0
        best_entry   = None
        best_xl_name = ""

        for entry in xl_entries:
            for xl_name in entry["names"]:
                score = _sim(hotel.name, xl_name)
                if score > best_score:
                    best_score   = score
                    best_entry   = entry
                    best_xl_name = xl_name

        if best_score >= THRESHOLD and best_entry:
            new_rooms = best_entry["rooms"]
            new_type  = best_entry["property_type"]
            old_rooms = hotel.room_count
            old_type  = hotel.property_type

            changed_rooms = new_rooms != old_rooms
            # Update property_type only if the Excel has a real value and DB still
            # shows the default placeholder "Unknown"
            changed_type  = (
                new_type is not None
                and (old_type in (None, "Unknown") or old_type != new_type)
            )
            if changed_rooms:
                hotel.room_count = new_rooms
            if changed_type:
                hotel.property_type = new_type

            # Note: this Excel is a room-count list, not a reliable signal of
            # which hotels actually transact with Alsabini as a vendor — the
            # is_alsabini flag is instead recomputed from booking data (see
            # upload.py, after the daily-bookings sync) so it matches the
            # same "Alsabini S.A. is a vendor on this hotel" criterion used
            # for the Alsabini revenue segment split.
            if changed_rooms or changed_type:
                updated_list.append({
                    "hotel_id":      hotel.id,
                    "hotel_name":    hotel.name,
                    "matched_to":    best_xl_name,
                    "score":         round(best_score, 2),
                    "old_rooms":     old_rooms,
                    "new_rooms":     new_rooms,
                    "old_type":      old_type,
                    "new_type":      new_type,
                })
            else:
                skipped_list.append({
                    "hotel_name": hotel.name,
                    "rooms":      old_rooms,
                    "type":       old_type,
                    "reason":     "already correct",
                })
        else:
            unmatched_list.append({
                "hotel_name":     hotel.name,
                "best_score":     round(best_score, 2),
                "best_candidate": best_xl_name,
            })

    db.commit()

    return {
        "updated":          len(updated_list),
        "skipped":          len(skipped_list),
        "unmatched":        len(unmatched_list),
        "updates":          updated_list,
        "no_change":        skipped_list,
        "unmatched_hotels": unmatched_list,
    }
