"""
Milestone / threshold alert system.

After each weekly Sync Sheets run, `run_alerts(db)` evaluates the portfolio
against a set of thresholds and emails any that fired to every registered
subscriber (via Brevo). Alerts:

  • Runway drops below 9 months            (edge-triggered)
  • GMV crosses €1M                        (one-time milestone)
  • SaaS MRR hits €5K                      (one-time milestone)
  • A hotel goes inactive (churn signal)   (week-on-week)
  • Weekly GMV drops >20% vs prior week    (week-on-week)

De-duplication: one-time milestones fire once (state remembers they fired);
the runway alert re-arms when runway recovers above 9; week-on-week checks run
once per new completed week. Sending is best-effort — a Brevo failure is logged
and retried on the next sync, and the dashboard never breaks because of it.

Email is sent only when BREVO_API_KEY is configured; otherwise alerts are
computed and logged but not emailed (so the system is safe before setup).
"""

import os
import json
import hmac
import hashlib
import urllib.parse
import urllib.request
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    AlertSubscriber, AlertState, WeeklyPerformance, Hotel, FinancialSnapshot,
)

# ── Thresholds ───────────────────────────────────────────────────────────────
RUNWAY_MONTHS_MIN = 9
GMV_MILESTONE     = 1_000_000
MRR_MILESTONE     = 5_000
WEEKLY_GMV_DROP   = 0.20   # >20% week-on-week drop


# ── Alert state (key/value) ──────────────────────────────────────────────────
def _get_state(db: Session, key: str):
    row = db.get(AlertState, key)
    return row.value if row else None


def _set_state(db: Session, key: str, value: str):
    row = db.get(AlertState, key)
    if row:
        row.value = value
    else:
        db.add(AlertState(key=key, value=value))


def _mk(kind: str, title: str, message: str) -> dict:
    return {"type": kind, "title": title, "message": message}


# ── Metric helpers ───────────────────────────────────────────────────────────
def _completed_weeks(db: Session):
    today = date.today()
    weeks = sorted({r[0] for r in db.query(WeeklyPerformance.week_start_date).distinct().all()})
    return [w for w in weeks if w + timedelta(days=6) < today]


def _week_gmv(db: Session, wk: date) -> float:
    return db.query(func.coalesce(func.sum(WeeklyPerformance.gmv), 0.0)).filter(
        WeeklyPerformance.week_start_date == wk
    ).scalar() or 0.0


def _active_hotels_in_week(db: Session, wk: date) -> set:
    rows = (
        db.query(Hotel.name)
          .join(WeeklyPerformance, WeeklyPerformance.hotel_id == Hotel.id)
          .filter(WeeklyPerformance.week_start_date == wk,
                  WeeklyPerformance.transactions > 0)
          .all()
    )
    return {r[0] for r in rows}


# ── Evaluation ───────────────────────────────────────────────────────────────
def evaluate_alerts(db: Session) -> list:
    """
    Returns the list of alerts that fired this run and stages the matching
    state changes in the session (caller commits after a successful send).

    The very first evaluation is a silent baseline: it records the current state
    (so milestones already crossed in the past don't fire retroactively) and
    emits nothing. Genuine crossings on subsequent runs alert as normal.
    """
    baselined = _get_state(db, "baselined") == "true"
    alerts: list = []

    # ── Milestones + runway (idempotent via state) ──
    try:
        from .kpi_engine import get_portfolio_summary
        summary = get_portfolio_summary(db)
        gmv_total = summary.total_gmv_season or 0
        mrr = summary.saas_mrr or 0
    except Exception as exc:
        print(f"[alerts] summary fetch failed: {exc}")
        gmv_total, mrr = None, None

    if gmv_total is not None and gmv_total >= GMV_MILESTONE and _get_state(db, "gmv_1m_fired") != "true":
        alerts.append(_mk("gmv_1m", "🎉 Milestone: GMV crossed €1M",
                          f"Total GMV has crossed €1,000,000 — now €{gmv_total:,.0f}."))
        _set_state(db, "gmv_1m_fired", "true")

    if mrr is not None and mrr >= MRR_MILESTONE and _get_state(db, "mrr_5k_fired") != "true":
        alerts.append(_mk("mrr_5k", "🎉 Milestone: SaaS MRR hit €5K",
                          f"SaaS MRR has reached €{mrr:,.0f} (threshold €5,000)."))
        _set_state(db, "mrr_5k_fired", "true")

    snap = db.query(FinancialSnapshot).order_by(FinancialSnapshot.snapshot_date.desc()).first()
    if snap and snap.runway_months is not None:
        now_below = snap.runway_months < RUNWAY_MONTHS_MIN
        was_below = _get_state(db, "runway_below_9") == "true"
        if now_below and not was_below:
            alerts.append(_mk("runway_9", "⚠️ Runway below 9 months",
                              f"Cash runway has dropped to {snap.runway_months:.1f} months "
                              f"(threshold {RUNWAY_MONTHS_MIN})."))
        _set_state(db, "runway_below_9", "true" if now_below else "false")

    # ── Week-on-week checks (once per new completed week) ──
    weeks = _completed_weeks(db)
    if len(weeks) >= 2:
        this_wk, prior_wk = weeks[-1], weeks[-2]
        if _get_state(db, "last_weekly_eval_week") != this_wk.isoformat():
            this_gmv, prior_gmv = _week_gmv(db, this_wk), _week_gmv(db, prior_wk)
            if prior_gmv > 0 and this_gmv < prior_gmv * (1 - WEEKLY_GMV_DROP):
                drop = (1 - this_gmv / prior_gmv) * 100
                alerts.append(_mk("gmv_drop", f"⚠️ Weekly GMV dropped {drop:.0f}%",
                                  f"GMV fell from €{prior_gmv:,.0f} to €{this_gmv:,.0f} "
                                  f"week-on-week (week of {this_wk.isoformat()})."))

            this_active = _active_hotels_in_week(db, this_wk)
            prior_active = _active_hotels_in_week(db, prior_wk)
            churned = sorted(prior_active - this_active)
            if churned:
                shown = ", ".join(churned[:12])
                more = f" (+{len(churned) - 12} more)" if len(churned) > 12 else ""
                alerts.append(_mk("churn", f"⚠️ {len(churned)} hotel(s) went inactive",
                                  f"Had bookings the prior week but none in the week of "
                                  f"{this_wk.isoformat()}: {shown}{more}."))

            _set_state(db, "last_weekly_eval_week", this_wk.isoformat())

    if not baselined:
        # First run: state is now recorded; suppress all (possibly retroactive) alerts.
        _set_state(db, "baselined", "true")
        return []

    return alerts


# ── Unsubscribe links (secure, no login needed) ──────────────────────────────
def _unsub_secret() -> str:
    return (os.getenv("ALERT_UNSUB_SECRET") or os.getenv("SYNC_TOKEN")
            or os.getenv("DASHBOARD_PASS") or "bookinguru-alerts-secret")


def unsub_token(email: str) -> str:
    """HMAC token so an unsubscribe link only works for its own email (unforgeable)."""
    return hmac.new(_unsub_secret().encode(), email.strip().lower().encode(),
                    hashlib.sha256).hexdigest()[:32]


def _unsub_url(email: str) -> str:
    base = os.getenv("PUBLIC_API_URL", "https://bookinguru-dashboard.onrender.com/api").rstrip("/")
    q = urllib.parse.urlencode({"email": email, "token": unsub_token(email)})
    return f"{base}/alerts/u?{q}"


# ── Email (Brevo) ────────────────────────────────────────────────────────────
def _email_html(alert: dict, unsub_url: str) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:auto">
      <div style="border-left:4px solid #2563eb;padding:14px 18px;background:#f8fafc;border-radius:6px">
        <h2 style="margin:0 0 8px;font-size:17px;color:#0f172a">{alert['title']}</h2>
        <p style="margin:0;font-size:14px;color:#334155;line-height:1.5">{alert['message']}</p>
      </div>
      <p style="font-size:11px;color:#94a3b8;margin-top:14px">
        BookinGuru automated alert · triggered after the weekly data sync.<br>
        <a href="{unsub_url}" style="color:#94a3b8;text-decoration:underline">Unsubscribe from these alerts</a>
      </p>
    </div>"""


def _brevo_send(api_key: str, subject: str, html: str, recipient: str, unsub_url: str = None):
    sender_email = os.getenv("ALERT_SENDER_EMAIL", "alerts@bookinguru.com")
    sender_name  = os.getenv("ALERT_SENDER_NAME", "BookinGuru Alerts")
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to":  [{"email": recipient}],
        "subject": subject,
        "htmlContent": html,
    }
    if unsub_url:
        # RFC 8058 one-click unsubscribe (Gmail/Outlook show a native button).
        payload["headers"] = {
            "List-Unsubscribe": f"<{unsub_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def _send_to_each(api_key: str, subject: str, alert: dict, recipients: list):
    """Send one personalised email (with its own unsubscribe link) per recipient."""
    for e in recipients:
        try:
            url = _unsub_url(e)
            _brevo_send(api_key, subject, _email_html(alert, url), e, url)
        except Exception as exc:
            print(f"[alerts] send to {e} failed: {exc}")


def send_alerts(db: Session, alerts: list):
    recipients = [s.email for s in db.query(AlertSubscriber).filter(AlertSubscriber.active == True).all()]  # noqa: E712
    if not recipients:
        print(f"[alerts] {len(alerts)} alert(s) fired but no subscribers registered.")
        return
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        print(f"[alerts] {len(alerts)} alert(s) fired but BREVO_API_KEY is not set — not emailed.")
        return
    for a in alerts:
        _send_to_each(api_key, a["title"], a, recipients)


def run_alerts(db: Session) -> list:
    """Evaluate, send (best-effort), and persist state. Returns alerts that fired."""
    alerts = evaluate_alerts(db)
    try:
        if alerts:
            send_alerts(db, alerts)
        db.commit()   # persist state (fired flags / last-eval week / runway state)
    except Exception as exc:
        db.rollback()
        print(f"[alerts] send/commit failed — will retry next sync: {exc}")
        return []
    return alerts


def send_test_email(db: Session) -> dict:
    """Send a sample alert to all subscribers to verify Brevo configuration."""
    recipients = [s.email for s in db.query(AlertSubscriber).filter(AlertSubscriber.active == True).all()]  # noqa: E712
    if not recipients:
        return {"sent": False, "reason": "No subscribers registered."}
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        return {"sent": False, "reason": "BREVO_API_KEY is not set on the server."}
    sample = _mk("test", "✅ BookinGuru alerts are working",
                 "This is a test of the alert system. You'll receive messages here when a "
                 "key threshold is hit after the weekly data sync.")
    _send_to_each(api_key, sample["title"], sample, recipients)
    return {"sent": True, "recipients": len(recipients)}


def alert_status(db: Session) -> dict:
    """Read-only snapshot of current metrics vs thresholds (no state change)."""
    try:
        from .kpi_engine import get_portfolio_summary
        summary = get_portfolio_summary(db)
        gmv_total = summary.total_gmv_season or 0
        mrr = summary.saas_mrr or 0
    except Exception:
        gmv_total, mrr = None, None
    snap = db.query(FinancialSnapshot).order_by(FinancialSnapshot.snapshot_date.desc()).first()
    runway = snap.runway_months if snap else None
    return {
        "gmv_total": gmv_total, "gmv_threshold": GMV_MILESTONE,
        "gmv_milestone_hit": gmv_total is not None and gmv_total >= GMV_MILESTONE,
        "mrr": mrr, "mrr_threshold": MRR_MILESTONE,
        "mrr_milestone_hit": mrr is not None and mrr >= MRR_MILESTONE,
        "runway_months": runway, "runway_threshold": RUNWAY_MONTHS_MIN,
        "runway_below_threshold": runway is not None and runway < RUNWAY_MONTHS_MIN,
        "subscribers": db.query(AlertSubscriber).filter(AlertSubscriber.active == True).count(),  # noqa: E712
        "email_configured": bool(os.getenv("BREVO_API_KEY")),
    }
