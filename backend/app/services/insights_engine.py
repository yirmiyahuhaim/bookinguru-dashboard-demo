"""
Weekly Insights engine.

Computes week-over-week movements for hotels and vendors so the team can spot
what grew or declined sharply and follow up with the hotel / vendor.

Two layers:
  1. A deterministic delta engine (always runs — free, reliable, never invents
     numbers). Compares the latest *completed* week against the prior week AND
     against the trailing 4-week average, filters out low-volume noise, and
     ranks the biggest movers (declines first).
  2. A narrative layer (`generate_narrative`) that turns those computed deltas
     into a readable, prioritised brief. Rule-based by default (free, no API
     key, no data leaves the server). If a future owner sets the env vars
     INSIGHTS_AI=anthropic + ANTHROPIC_API_KEY, it switches to Claude-written
     prose — the numbers are always the deterministic ones, so the model only
     ever rephrases pre-computed figures (it cannot hallucinate a number).
"""

import os
from datetime import date, timedelta
from collections import defaultdict

from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from ..models import DailyBooking, WeeklyPerformance, Hotel


# ── Tuning knobs ─────────────────────────────────────────────────────────────
AVG_WEEKS          = 4      # trailing weeks for the "vs average" comparison
MIN_VENDOR_BOOKINGS = 5     # ignore vendors below this volume (avoids 1→0 spam)
MIN_HOTEL_BOOKINGS  = 3     # ignore hotels below this weekly booking volume
TOP_DECLINES        = 5     # how many declines to surface per entity type
TOP_GROWTH          = 3     # how many growth movers to surface per entity type
SHARP_PCT           = 20.0  # |%| move that counts as "sharp" week-on-week


def _week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _latest_complete_week(max_date: date, today: date) -> date:
    """
    Latest week that (a) has data and (b) is calendar-complete.
    Steps back one week if max_date falls in the current in-progress week,
    so a partial week never looks like a decline.
    """
    wk = _week_start(max_date)
    if wk + timedelta(days=6) >= today:      # current week not finished yet
        wk = wk - timedelta(days=7)
    return wk


def _pct(curr: float, base: float):
    """% change curr vs base; None when base is 0 (new / returning activity)."""
    if base == 0:
        return None
    return round((curr - base) / base * 100, 1)


def _build_records(series: dict, this_wk: date, prior_wk: date, avg_weeks_starts,
                   primary_key: str, min_volume: int):
    """
    series: { entity_name: { week_start: {metric: value, ...} } }
    Returns (declines, growth) lists of record dicts, ranked.
    primary_key drives ranking & the headline figure ("bookings" or "gmv").
    """
    records = []
    for name, by_week in series.items():
        this_vals  = by_week.get(this_wk,  {})
        prior_vals = by_week.get(prior_wk, {})

        this_p  = this_vals.get(primary_key, 0)
        prior_p = prior_vals.get(primary_key, 0)

        # Trailing N-week average for the primary metric (missing week = 0)
        avg_samples = [by_week.get(w, {}).get(primary_key, 0) for w in avg_weeks_starts]
        avg_p = sum(avg_samples) / len(avg_samples) if avg_samples else 0

        # Volume gate — skip entities too small to be worth a conversation
        if max(this_p, prior_p, avg_p) < min_volume:
            continue
        # Nothing happening at all
        if this_p == 0 and prior_p == 0:
            continue

        rec = {
            "name": name,
            "this": round(this_p, 2),
            "prior": round(prior_p, 2),
            "avg": round(avg_p, 2),
            "wow_pct": _pct(this_p, prior_p),
            "vs_avg_pct": _pct(this_p, avg_p),
            "is_new": prior_p == 0 and this_p > 0,
            # carry secondary metrics for display context
            "this_secondary": {k: round(v, 2) for k, v in this_vals.items() if k != primary_key},
        }
        records.append(rec)

    declines = [r for r in records if r["this"] < r["prior"]]
    growth   = [r for r in records if r["this"] > r["prior"]]

    # Rank declines by largest absolute drop in the primary metric
    declines.sort(key=lambda r: (r["this"] - r["prior"]))
    # Rank growth by largest absolute gain
    growth.sort(key=lambda r: (r["prior"] - r["this"]))

    return declines[:TOP_DECLINES], growth[:TOP_GROWTH]


# ── Data gathering ───────────────────────────────────────────────────────────

def _vendor_series(db: Session, window_start: date, window_end: date) -> dict:
    """{ vendor_name: { week_start: {bookings, gmv} } } over the window."""
    bq = db.query(DailyBooking).filter(
        DailyBooking.company_name.isnot(None),
        DailyBooking.company_name != "",
        DailyBooking.reservation_date >= window_start,
        DailyBooking.reservation_date <= window_end,
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
    )
    series: dict = defaultdict(lambda: defaultdict(lambda: {"bookings": 0, "gmv": 0.0}))
    for b in bq.all():
        wk = _week_start(b.reservation_date)
        cell = series[b.company_name][wk]
        cell["bookings"] += 1
        cell["gmv"] += b.total_paid or 0.0
    return series


def _hotel_series(db: Session, window_start: date, window_end: date) -> dict:
    """{ hotel_name: { week_start: {gmv, net_revenue, bookings} } } over the window."""
    rows = (
        db.query(WeeklyPerformance, Hotel.name)
          .join(Hotel, Hotel.id == WeeklyPerformance.hotel_id)
          .filter(
              WeeklyPerformance.week_start_date >= window_start,
              WeeklyPerformance.week_start_date <= window_end,
          )
          .all()
    )
    series: dict = defaultdict(lambda: defaultdict(lambda: {"gmv": 0.0, "net_revenue": 0.0, "bookings": 0}))
    for perf, hotel_name in rows:
        wk = _week_start(perf.week_start_date)
        cell = series[hotel_name][wk]
        cell["gmv"] += perf.gmv or 0.0
        cell["net_revenue"] += perf.bg_gross_revenue or 0.0
        cell["bookings"] += perf.transactions or 0
    return series


def get_weekly_insights(db: Session, week=None, date_from=None, date_to=None) -> dict:
    """
    Top-level entry point — returns the full insights payload (see module docstring).

    `week` (optional) selects a specific week to analyse (any Monday week-start);
    defaults to the latest completed week. `date_from`/`date_to` scope the list of
    selectable weeks to the portfolio time range.
    """
    today = date.today()

    # Universe of selectable weeks = completed weeks of hotel data, within the
    # portfolio range. These populate the week selector in the UI.
    wq = db.query(WeeklyPerformance.week_start_date).distinct()
    if date_from: wq = wq.filter(WeeklyPerformance.week_start_date >= date_from)
    if date_to:   wq = wq.filter(WeeklyPerformance.week_start_date <= date_to)
    all_weeks = sorted({r[0] for r in wq.all()})
    completed = [w for w in all_weeks if w + timedelta(days=6) < today]
    available = completed or all_weeks   # if everything is the current week, allow it
    if not available:
        return {"available": False, "reason": "No weekly data for this period yet."}

    # Resolve the week to analyse (normalise any chosen date to its Monday).
    this_wk = None
    if week is not None:
        wd = date.fromisoformat(week) if isinstance(week, str) else week
        wd = wd - timedelta(days=wd.weekday())
        if wd in available:
            this_wk = wd
    if this_wk is None:
        this_wk = available[-1]   # latest completed week in range

    prior_wk = this_wk - timedelta(days=7)
    avg_weeks_starts = [this_wk - timedelta(days=7 * (i + 1)) for i in range(AVG_WEEKS)]

    window_start = this_wk - timedelta(days=7 * AVG_WEEKS)
    window_end   = this_wk + timedelta(days=6)

    vendor_series = _vendor_series(db, window_start, window_end)
    hotel_series  = _hotel_series(db, window_start, window_end)

    v_declines, v_growth = _build_records(
        vendor_series, this_wk, prior_wk, avg_weeks_starts,
        primary_key="bookings", min_volume=MIN_VENDOR_BOOKINGS,
    )
    h_declines, h_growth = _build_records(
        hotel_series, this_wk, prior_wk, avg_weeks_starts,
        primary_key="gmv", min_volume=MIN_HOTEL_BOOKINGS,
    )

    payload = {
        "available": True,
        "this_week": this_wk.isoformat(),
        "prior_week": prior_wk.isoformat(),
        "avg_weeks": AVG_WEEKS,
        "available_weeks": [w.isoformat() for w in available],   # for the week selector
        "hotels":  {"declines": h_declines, "growth": h_growth, "metric": "gmv"},
        "vendors": {"declines": v_declines, "growth": v_growth, "metric": "bookings"},
        "yoy": _yoy_movers(db, this_wk),
        "first_time_hotels": _first_time_hotels(db, this_wk, prior_wk, avg_weeks_starts),
    }
    payload["narrative"], payload["generated_by"] = generate_narrative(payload)
    return payload


def _first_time_hotels(db: Session, this_wk: date, prior_wk: date, avg_weeks_starts) -> dict:
    """
    Count hotels that made their FIRST-EVER purchase (first week with a paid
    booking) in a given week — the new-hotel onboarding signal. Compares the
    analysed week to the prior week and the trailing 4-week average.
    """
    # First active week per hotel = earliest week_start where transactions > 0.
    rows = (
        db.query(WeeklyPerformance.hotel_id, func.min(WeeklyPerformance.week_start_date))
          .filter(WeeklyPerformance.transactions > 0)
          .group_by(WeeklyPerformance.hotel_id)
          .all()
    )
    first_week_counts: dict = defaultdict(int)
    for _hid, first_wk in rows:
        first_week_counts[first_wk] += 1

    this_n  = first_week_counts.get(this_wk, 0)
    prior_n = first_week_counts.get(prior_wk, 0)
    avg = (sum(first_week_counts.get(w, 0) for w in avg_weeks_starts) / len(avg_weeks_starts)
           if avg_weeks_starts else 0)
    return {"this": this_n, "prior": prior_n, "avg": round(avg, 1), "avg_weeks": len(avg_weeks_starts)}


def _yoy_records(this_map: dict, ly_map: dict, compare_key: str, gate_key: str, min_volume: int):
    """Build (declines, growth) comparing this-season vs last-season per entity."""
    records = []
    for name in set(this_map) | set(ly_map):
        t = this_map.get(name, {compare_key: 0, gate_key: 0})
        l = ly_map.get(name, {compare_key: 0, gate_key: 0})
        if max(t.get(gate_key, 0), l.get(gate_key, 0)) < min_volume:
            continue
        records.append({
            "name": name,
            "this": round(t.get(compare_key, 0), 2),
            "prior": round(l.get(compare_key, 0), 2),   # last season's value
            "avg": 0,
            "wow_pct": _pct(t.get(compare_key, 0), l.get(compare_key, 0)),  # reused field = YoY %
            "vs_avg_pct": None,
            "is_new": l.get(compare_key, 0) == 0 and t.get(compare_key, 0) > 0,
        })
    declines = sorted([r for r in records if r["this"] < r["prior"]],
                      key=lambda r: (r["this"] - r["prior"]))[:TOP_DECLINES]
    growth   = sorted([r for r in records if r["this"] > r["prior"]],
                      key=lambda r: (r["prior"] - r["this"]))[:TOP_GROWTH]
    return declines, growth


def _yoy_movers(db: Session, this_wk: date) -> dict:
    """
    Year-on-year: compare the chosen week to the SAME week last season (364 days
    earlier — preserves week-of-year and day-of-week). Flags both hotels (GMV)
    and vendors (bookings) that declined or grew vs last year.
    """
    ly_wk = this_wk - timedelta(days=364)

    # ── Hotels (WeeklyPerformance) ──
    h_rows = (
        db.query(WeeklyPerformance, Hotel.name)
          .join(Hotel, Hotel.id == WeeklyPerformance.hotel_id)
          .filter(WeeklyPerformance.week_start_date.in_([this_wk, ly_wk]))
          .all()
    )
    h_this: dict = defaultdict(lambda: {"gmv": 0.0, "bookings": 0})
    h_ly:   dict = defaultdict(lambda: {"gmv": 0.0, "bookings": 0})
    for perf, name in h_rows:
        tgt = h_this if perf.week_start_date == this_wk else h_ly
        tgt[name]["gmv"] += perf.gmv or 0.0
        tgt[name]["bookings"] += perf.transactions or 0

    # ── Vendors (DailyBooking — daily rows in each week's Mon–Sun range) ──
    this_end, ly_end = this_wk + timedelta(days=6), ly_wk + timedelta(days=6)
    v_rows = db.query(DailyBooking).filter(
        DailyBooking.company_name.isnot(None),
        DailyBooking.company_name != "",
        or_(
            DailyBooking.reservation_status.is_(None),
            DailyBooking.reservation_status != "Cancelled",
        ),
        or_(
            and_(DailyBooking.reservation_date >= this_wk, DailyBooking.reservation_date <= this_end),
            and_(DailyBooking.reservation_date >= ly_wk,   DailyBooking.reservation_date <= ly_end),
        ),
    ).all()
    v_this: dict = defaultdict(lambda: {"bookings": 0, "gmv": 0.0})
    v_ly:   dict = defaultdict(lambda: {"bookings": 0, "gmv": 0.0})
    for b in v_rows:
        tgt = v_this if this_wk <= b.reservation_date <= this_end else v_ly
        tgt[b.company_name]["bookings"] += 1
        tgt[b.company_name]["gmv"] += b.total_paid or 0.0

    if not h_ly and not v_ly:
        # No data for the same week last season — nothing to compare against.
        return {
            "available": False, "ly_week": ly_wk.isoformat(),
            "hotels":  {"declines": [], "growth": [], "metric": "gmv"},
            "vendors": {"declines": [], "growth": [], "metric": "bookings"},
        }

    h_decl, h_grow = _yoy_records(h_this, h_ly, compare_key="gmv",      gate_key="bookings", min_volume=MIN_HOTEL_BOOKINGS)
    v_decl, v_grow = _yoy_records(v_this, v_ly, compare_key="bookings", gate_key="bookings", min_volume=MIN_VENDOR_BOOKINGS)
    return {
        "available": True, "ly_week": ly_wk.isoformat(),
        "hotels":  {"declines": h_decl, "growth": h_grow, "metric": "gmv"},
        "vendors": {"declines": v_decl, "growth": v_grow, "metric": "bookings"},
    }


# ── Narrative layer ──────────────────────────────────────────────────────────

def _fmt_eur(v) -> str:
    return f"€{round(v):,}"


def _fmt_metric(value, metric: str) -> str:
    return _fmt_eur(value) if metric == "gmv" else f"{int(round(value))}"


def _metric_word(metric: str) -> str:
    return "GMV" if metric == "gmv" else "bookings"


def _fmt_week_label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%-d %b") if os.name != "nt" else d.strftime("%#d %b")


def _decline_sentence(rec: dict, metric: str) -> str:
    word = _metric_word(metric)
    this_s  = _fmt_metric(rec["this"], metric)
    prior_s = _fmt_metric(rec["prior"], metric)
    parts = [f"**{rec['name']}** — {word} "]
    if rec["wow_pct"] is not None:
        parts.append(f"fell {abs(rec['wow_pct']):.0f}% week-on-week ({prior_s} → {this_s})")
    else:
        parts.append(f"dropped to {this_s} (from {prior_s})")
    if rec["vs_avg_pct"] is not None and rec["vs_avg_pct"] < -5:
        parts.append(f", and is running {abs(rec['vs_avg_pct']):.0f}% below its {AVG_WEEKS}-week average — a sustained slide worth raising")
    else:
        parts.append(" — a sharp week-on-week drop")
    parts.append(".")
    return "".join(parts)


def _growth_sentence(rec: dict, metric: str) -> str:
    word = _metric_word(metric)
    this_s  = _fmt_metric(rec["this"], metric)
    prior_s = _fmt_metric(rec["prior"], metric)
    if rec["is_new"]:
        return f"**{rec['name']}** — newly active this week with {this_s} {word}."
    parts = [f"**{rec['name']}** — {word} "]
    if rec["wow_pct"] is not None:
        parts.append(f"up {rec['wow_pct']:.0f}% ({prior_s} → {this_s})")
    else:
        parts.append(f"grew to {this_s}")
    if rec["vs_avg_pct"] is not None and rec["vs_avg_pct"] > 5:
        parts.append(f", well above its {AVG_WEEKS}-week average")
    parts.append(".")
    return "".join(parts)


def _narrate_rules(payload: dict) -> str:
    """Free, deterministic prose brief built from the computed deltas."""
    wk   = _fmt_week_label(payload["this_week"])
    pwk  = _fmt_week_label(payload["prior_week"])
    lines = [f"**Week of {wk} vs {pwk}** (also compared to the trailing {payload['avg_weeks']}-week average).", ""]

    declines = (
        [( "hotel",  r) for r in payload["hotels"]["declines"]]
        + [("vendor", r) for r in payload["vendors"]["declines"]]
    )
    growth = (
        [( "hotel",  r) for r in payload["hotels"]["growth"]]
        + [("vendor", r) for r in payload["vendors"]["growth"]]
    )

    if declines:
        lines.append("⚠️ **Worth a conversation this week:**")
        for kind, rec in declines:
            metric = payload["hotels"]["metric"] if kind == "hotel" else payload["vendors"]["metric"]
            tag = "{{hotel}}" if kind == "hotel" else "{{vendor}}"   # leading colour-coded tag (rendered by frontend)
            lines.append(f"- {tag}{_decline_sentence(rec, metric)}")
        lines.append("")

    if growth:
        lines.append("📈 **Growing fast:**")
        for kind, rec in growth:
            metric = payload["hotels"]["metric"] if kind == "hotel" else payload["vendors"]["metric"]
            tag = "{{hotel}}" if kind == "hotel" else "{{vendor}}"   # leading colour-coded tag (rendered by frontend)
            lines.append(f"- {tag}{_growth_sentence(rec, metric)}")
        lines.append("")

    # ── Year-on-year (vs same week last season) — hotels and vendors ──────────
    yoy = payload.get("yoy", {})
    yoy_declines = []
    if yoy.get("available"):
        yoy_declines = (
            [("hotel",  r) for r in yoy["hotels"]["declines"]]
            + [("vendor", r) for r in yoy["vendors"]["declines"]]
        )
    if yoy_declines:
        ly_lbl = _fmt_week_label(yoy["ly_week"])
        lines.append(f"📉 **Down vs last season** (this week vs the week of {ly_lbl} last year):")
        for kind, rec in yoy_declines:
            metric = "gmv" if kind == "hotel" else "bookings"
            word   = _metric_word(metric)
            tag    = "{{hotel}}" if kind == "hotel" else "{{vendor}}"
            this_s  = _fmt_metric(rec["this"], metric)
            prior_s = _fmt_metric(rec["prior"], metric)
            if rec["wow_pct"] is not None:
                trend = f"{word} down {abs(rec['wow_pct']):.0f}% ({prior_s} last season → {this_s} now)"
            else:
                trend = f"{word} dropped to {this_s} (from {prior_s} last season)"
            lines.append(f"- {tag}**{rec['name']}** — {trend}.")
        lines.append("")

    if not declines and not growth and not yoy_declines:
        lines.append("Nothing moved sharply enough this week to flag. Steady week across hotels and vendors.")

    return "\n".join(lines).strip()


def _narrate_with_claude(payload: dict) -> str:
    """
    Optional upgrade path — real LLM-written prose. Only runs when
    INSIGHTS_AI=anthropic and a key is configured AND the `anthropic` package
    is installed. The model is given ONLY the pre-computed figures and told to
    rephrase them — it never sees raw data and cannot invent numbers.
    Falls back to the rule-based brief on any error so the dashboard never
    breaks because of an AI hiccup.
    """
    try:
        import anthropic  # lazy import — not a hard dependency of the app
    except ImportError:
        return _narrate_rules(payload)

    model = os.getenv("INSIGHTS_LLM_MODEL", "claude-opus-4-8")
    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        system = (
            "You are a revenue analyst for a hotel-tech company. You will be given "
            "PRE-COMPUTED week-over-week figures for hotels and vendors. Write a short, "
            "prioritised brief (markdown, a few bullets) that leads with declines worth "
            "investigating, then notable growth. Use ONLY the numbers provided — never "
            "invent or estimate figures. Be concrete and action-oriented; the reader will "
            "use this to decide which hotel or vendor to call. Keep it under 180 words."
        )
        resp = client.messages.create(
            model=model,
            max_tokens=1200,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": _claude_input(payload)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        return text or _narrate_rules(payload)
    except Exception:
        # Any API/network/quota issue → silently fall back to the free brief.
        return _narrate_rules(payload)


def _claude_input(payload: dict) -> str:
    """Render the computed deltas as a compact text block for the model."""
    import json
    return (
        f"Comparison: week of {payload['this_week']} vs prior week {payload['prior_week']}, "
        f"and vs the trailing {payload['avg_weeks']}-week average.\n\n"
        f"Hotels (metric=GMV in EUR):\n{json.dumps(payload['hotels'], indent=2)}\n\n"
        f"Vendors (metric=bookings count):\n{json.dumps(payload['vendors'], indent=2)}\n\n"
        f"Year-on-year vs same week last season (hotels metric=GMV, vendors "
        f"metric=bookings; 'prior'=last season's value):\n{json.dumps(payload.get('yoy', {}), indent=2)}\n\n"
        "Write the brief now, including a short 'vs last season' note for any year-on-year hotel or vendor declines."
    )


def generate_narrative(payload: dict):
    """
    Returns (narrative_markdown, generated_by).
    Seam between free rule-based prose and the optional Claude upgrade.
    """
    if os.getenv("INSIGHTS_AI", "").lower() == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        return _narrate_with_claude(payload), "ai"
    return _narrate_rules(payload), "rules"
