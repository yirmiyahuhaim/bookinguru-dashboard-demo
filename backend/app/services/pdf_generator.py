from datetime import date
from typing import List, Optional
from ..schemas import PortfolioSummary, HotelKPIs


# ── Formatting helpers ───────────────────────────────────────────────────────
def _eur(v, decimals: int = 0) -> str:
    if v is None:
        return "—"
    return f"€{v:,.{decimals}f}"


def _pct(v, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}%"


def _num(v) -> str:
    if v is None:
        return "—"
    return f"{v:,}"


def _card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
      <div class="label">{label}</div>
      <div class="value">{value}</div>
      {sub_html}
    </div>"""


# ── Inline SVG GMV trend chart (prints without JS) ──────────────────────────
def _gmv_trend_svg(trend: List) -> str:
    """trend: list of objects with .week_start_date (str) and .gmv (float)."""
    pts = [(t.week_start_date, t.gmv or 0.0) for t in trend]
    if len(pts) < 2:
        return '<p style="color:#94a3b8;font-size:0.85rem">Not enough weekly data for a trend chart.</p>'

    W, H = 720, 240
    PAD_L, PAD_R, PAD_T, PAD_B = 56, 16, 14, 34
    iw, ih = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    max_v = max(v for _, v in pts) or 1.0

    def x(i): return PAD_L + iw * i / (len(pts) - 1)
    def y(v): return PAD_T + ih * (1 - v / max_v)

    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = f"{PAD_L},{PAD_T + ih} " + line + f" {PAD_L + iw:.1f},{PAD_T + ih}"

    def fmt_k(v):
        return f"€{v/1000:.0f}k" if v >= 1000 else f"€{v:.0f}"

    def fmt_d(iso):
        try:
            d = date.fromisoformat(str(iso)[:10])
            return d.strftime("%d %b")
        except ValueError:
            return str(iso)

    # Y gridlines at 0 / 50% / 100%; up to 6 X labels
    grid = ""
    for frac in (0.0, 0.5, 1.0):
        gy = PAD_T + ih * (1 - frac)
        grid += (f'<line x1="{PAD_L}" y1="{gy:.1f}" x2="{PAD_L + iw}" y2="{gy:.1f}" '
                 f'stroke="#e2e8f0" stroke-width="1"/>'
                 f'<text x="{PAD_L - 8}" y="{gy + 4:.1f}" text-anchor="end" '
                 f'font-size="10" fill="#94a3b8">{fmt_k(max_v * frac)}</text>')

    step = max(1, (len(pts) - 1) // 5)
    xlabels = ""
    for i in range(0, len(pts), step):
        xlabels += (f'<text x="{x(i):.1f}" y="{H - 12}" text-anchor="middle" '
                    f'font-size="10" fill="#94a3b8">{fmt_d(pts[i][0])}</text>')

    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.5" fill="#3b82f6"/>'
        for i, (_, v) in enumerate(pts)
    )

    return f"""
    <svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" xmlns="http://www.w3.org/2000/svg">
      {grid}
      <polygon points="{area}" fill="#3b82f6" opacity="0.10"/>
      <polyline points="{line}" fill="none" stroke="#3b82f6" stroke-width="2.5"
                stroke-linejoin="round" stroke-linecap="round"/>
      {dots}
      {xlabels}
    </svg>"""


# ── Per-hotel fact page ──────────────────────────────────────────────────────
def _hotel_page(h: HotelKPIs) -> str:
    cls = h.activity_class or "—"
    cards = (
        _card("GMV", _eur(h.total_gmv))
        + _card("Net Revenue", _eur(h.net_revenue))
        + _card("Take Rate", _pct(h.avg_take_rate))
        + _card("Attach Rate", _pct(h.attach_rate))
        + _card("ARPAR_BG", _eur(h.arpar_bg, 2))
        + _card("AOV", _eur(h.aov, 2))
        + _card("Paid Transactions", _num(h.total_transactions))
        + _card("Total Bookings", _num(h.total_bookings))
        + _card("Rooms", _num(h.room_count))
        + _card("SaaS MRR", _eur(h.saas_mrr))
        + _card("Activity Class", cls)
        + _card("Weeks of Data", _num(h.weeks_of_data))
    )
    if h.avg_incremental_revenue is not None:
        cards += _card("Incremental Revenue", _eur(h.avg_incremental_revenue))
    if h.avg_cancellation_rate is not None:
        cards += _card("Cancellation Rate", _pct(h.avg_cancellation_rate))
    if h.total_offers_generated is not None:
        cards += _card("Offers Generated", _num(h.total_offers_generated))
    if h.avg_offers_conversion is not None:
        cards += _card("Offers Conversion", _pct(h.avg_offers_conversion))

    status_colour = (
        "#16a34a" if h.pipeline_status == "Active"
        else "#d97706" if h.pipeline_status == "Pipeline"
        else "#dc2626"
    )
    return f"""
<div class="page hotel-page">
  <div class="hotel-head">
    <h2>{h.hotel_name}</h2>
    <div class="badges">
      <span class="badge">{h.market}</span>
      <span class="badge">{h.property_type}</span>
      <span class="badge">Class {cls}</span>
      <span class="badge" style="color:{status_colour};border-color:{status_colour}">{h.pipeline_status}</span>
    </div>
  </div>
  <div class="kpi-grid">{cards}</div>
  <div class="footer">BookinGuru Confidential · Hotel fact sheet</div>
</div>"""


# ── Main report builder ──────────────────────────────────────────────────────
def build_pdf_html(
    summary: PortfolioSummary,
    hotel_kpis: List[HotelKPIs],
    trend: Optional[List] = None,
    period_label: str = "Season to date",
) -> str:
    today = date.today().strftime("%d %B %Y")

    # Hotel list table (all hotels, active first)
    ordered = sorted(hotel_kpis, key=lambda k: (not k.is_active, -(k.total_gmv or 0)))
    hotel_rows = ""
    for h in ordered:
        status_colour = (
            "#16a34a" if h.pipeline_status == "Active"
            else "#d97706" if h.pipeline_status == "Pipeline"
            else "#dc2626"
        )
        hotel_rows += f"""
        <tr>
          <td>{h.hotel_name}</td>
          <td>{h.market}</td>
          <td>{h.property_type}</td>
          <td>{h.room_count}</td>
          <td>{_eur(h.total_gmv)}</td>
          <td>{_eur(h.net_revenue)}</td>
          <td>{_pct(h.avg_take_rate)}</td>
          <td>{_pct(h.attach_rate)}</td>
          <td>{h.activity_class or '—'}</td>
          <td style="color:{status_colour};font-weight:600">{h.pipeline_status}</td>
        </tr>"""

    # Portfolio summary — all top-level KPIs
    cls_sub = ""
    if summary.class_a_hotels is not None:
        cls_sub = f"A: {summary.class_a_hotels} · B: {summary.class_b_hotels} · C: {summary.class_c_hotels}"
    summary_cards = (
        _card("Active Hotels", _num(summary.total_active_hotels), cls_sub)
        + _card("Rooms Live", _num(summary.total_rooms_live))
        + _card("GMV", _eur(summary.total_gmv_season))
        + _card("Net Revenue", _eur(summary.total_net_revenue))
        + _card("Blended Take Rate", _pct(summary.blended_take_rate))
        + _card("SaaS MRR", _eur(summary.saas_mrr))
        + _card("ARPAR_BG", _eur(summary.avg_arpar_bg, 2) if summary.avg_arpar_bg is not None else "—")
        + _card("Attach Rate", _pct(summary.portfolio_attach_rate))
        + _card("AOV", _eur(summary.avg_aov, 2) if summary.avg_aov is not None else "—")
        + _card("Paid Transactions", _num(summary.total_paid_transactions))
        + _card("Total Bookings", _num(summary.total_bookings))
        + _card("Incremental Rev / Hotel", _eur(summary.avg_incremental_revenue))
    )
    if summary.runway_months is not None:
        summary_cards += (
            _card("Runway", f"{summary.runway_months:.1f} mo")
            + _card("Cash Balance", _eur(summary.cash_balance))
            + _card("Monthly Burn", _eur(summary.monthly_burn_rate))
        )

    trend_svg = _gmv_trend_svg(trend or [])
    active_pages = "".join(_hotel_page(h) for h in ordered if h.is_active)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<!-- Fixed-width layout viewport: mobile browsers (Safari iOS / Chrome Android)
     lay out print/PDF output using their normal viewport width unless told
     otherwise, which would squeeze this desktop-style report onto ~375px and
     break the grids/tables. Pinning it to 1024px makes the report render
     identically whether opened on a phone or a desktop before printing. -->
<meta name="viewport" content="width=1024"/>
<title>BookinGuru Investor Report — {today}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  @page {{ margin: 0; }}
  html {{ min-width: 1024px; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1e293b; min-width: 1024px; }}
  .cover {{ display:flex; flex-direction:column; justify-content:center;
            align-items:center; height:100vh; background:#0f172a; color:white;
            page-break-after:always; overflow:hidden; }}
  .cover .mark {{ width:72px; height:72px; border-radius:18px;
                  background:linear-gradient(135deg,#3b82f6,#4f46e5);
                  display:flex; align-items:center; justify-content:center;
                  font-size:2.2rem; font-weight:800; margin-bottom:1.4rem;
                  -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .cover h1 {{ font-size:2.8rem; font-weight:700; margin-bottom:0.5rem; }}
  .cover p  {{ font-size:1.1rem; color:#94a3b8; }}
  .confidential {{ margin-top:2rem; border:1px solid #ef4444; color:#ef4444;
                   padding:0.4rem 1.2rem; border-radius:4px; font-size:0.85rem;
                   letter-spacing:0.1em; }}
  .page {{ padding:40px 50px; page-break-after:always; }}
  .page:last-child {{ page-break-after:auto; }}
  h2 {{ font-size:1.4rem; color:#0f172a; margin-bottom:1.2rem;
        border-bottom:2px solid #3b82f6; padding-bottom:0.4rem; }}
  h3 {{ font-size:1.05rem; color:#0f172a; margin:1.6rem 0 0.8rem; }}
  .kpi-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
               margin-bottom:1.6rem; }}
  .kpi-card {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;
               padding:14px; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .kpi-card .label {{ font-size:0.72rem; color:#64748b; text-transform:uppercase;
                      letter-spacing:0.05em; margin-bottom:4px; }}
  .kpi-card .value {{ font-size:1.45rem; font-weight:700; color:#0f172a; }}
  .kpi-card .sub {{ font-size:0.7rem; color:#94a3b8; margin-top:3px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.76rem; }}
  th {{ background:#0f172a; color:white; padding:8px 10px; text-align:left;
        -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  td {{ padding:6px 10px; border-bottom:1px solid #e2e8f0; }}
  tr:nth-child(even) td {{ background:#f8fafc; }}
  .hotel-head {{ display:flex; align-items:baseline; justify-content:space-between;
                 gap:12px; flex-wrap:wrap; }}
  .badges {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:1rem; }}
  .badge {{ border:1px solid #cbd5e1; color:#475569; border-radius:999px;
            padding:2px 10px; font-size:0.72rem; }}
  .footer {{ margin-top:2rem; font-size:0.7rem; color:#94a3b8; text-align:center; }}
  .no-print {{ position:fixed; top:14px; right:14px; z-index:10; }}
  .no-print button {{ background:#2563eb; color:white; border:none; border-radius:8px;
                      padding:10px 18px; font-size:0.9rem; font-weight:600;
                      cursor:pointer; box-shadow:0 4px 14px rgba(0,0,0,.18); }}
  @media print {{ .no-print {{ display:none; }} }}
</style>
</head>
<body>

<div class="no-print">
  <button onclick="window.print()">Save as PDF</button>
</div>

<!-- Cover page -->
<div class="cover">
  <div class="mark">B</div>
  <h1>BookinGuru</h1>
  <p>Investor KPI Report</p>
  <p style="margin-top:0.5rem; color:#64748b">{today} · {period_label}</p>
  <div class="confidential">CONFIDENTIAL</div>
</div>

<!-- Portfolio summary -->
<div class="page">
  <h2>Portfolio Summary</h2>
  <div class="kpi-grid">{summary_cards}</div>

  <h3>GMV Trend — {period_label} (weekly)</h3>
  {trend_svg}

  <div class="footer">Generated {today} · BookinGuru Confidential · Do not distribute</div>
</div>

<!-- Hotel list -->
<div class="page">
  <h2>Hotel Portfolio</h2>
  <table>
    <thead>
      <tr>
        <th>Hotel</th><th>Market</th><th>Type</th><th>Rooms</th>
        <th>GMV</th><th>Net Rev</th><th>Take Rate</th>
        <th>Attach</th><th>Class</th><th>Status</th>
      </tr>
    </thead>
    <tbody>{hotel_rows}</tbody>
  </table>
  <div class="footer">Generated {today} · BookinGuru Confidential · Do not distribute</div>
</div>

<!-- One page per active hotel -->
{active_pages}

<script>
  // One-click export: open the print dialog automatically (Save as PDF).
  window.addEventListener('load', function () {{
    setTimeout(function () {{ window.print(); }}, 500);
  }});
</script>
</body>
</html>"""
