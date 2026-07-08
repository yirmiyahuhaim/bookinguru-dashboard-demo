"""
Google Analytics 4 service.
Credentials are loaded from the GA4_CREDENTIALS_JSON environment variable
(paste the full contents of the downloaded service-account JSON file).
Property ID is loaded from GA4_PROPERTY_ID (default: 419674066).
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "419674066")
GA4_CREDENTIALS_JSON = os.getenv("GA4_CREDENTIALS_JSON", "")


def _get_client():
    """Build a GA4 Data API client from the credentials env var."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account

    if not GA4_CREDENTIALS_JSON:
        raise ValueError("GA4_CREDENTIALS_JSON environment variable is not set")

    info = json.loads(GA4_CREDENTIALS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


def fetch_ga4_overview(period_days: int = 28) -> dict:
    """
    Returns:
      click_purchase_conversion  – purchase events / service page views × 100
      direct_sessions_pct        – % of sessions from Direct channel
      direct_sessions            – raw direct session count
      total_sessions             – total sessions
      purchase_events            – total purchase/booking events
      total_page_views           – total page views (service pages proxy)
      period_days                – the window used
      connected                  – True if GA4 responded successfully
      error                      – error message string if not connected
    """
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, Dimension, Metric, DateRange
        )

        client = _get_client()
        date_range = DateRange(start_date=f"{period_days}daysAgo", end_date="today")
        property_id = f"properties/{GA4_PROPERTY_ID}"

        # ── Request 1: overall sessions + purchase events ─────────────────
        req1 = RunReportRequest(
            property=property_id,
            date_ranges=[date_range],
            metrics=[
                Metric(name="sessions"),
                Metric(name="eventCount"),
                Metric(name="screenPageViews"),
            ],
            dimension_filter={
                "or_group": {
                    "expressions": [
                        {"filter": {"field_name": "eventName",
                                    "string_filter": {"value": "purchase"}}},
                    ]
                }
            },
        )

        # ── Request 2: sessions by channel group ──────────────────────────
        req2 = RunReportRequest(
            property=property_id,
            date_ranges=[date_range],
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions")],
        )

        # Run both
        resp1 = client.run_report(req1)
        resp2 = client.run_report(req2)

        # Parse request 1 — totals
        total_sessions = 0
        purchase_events = 0
        total_page_views = 0
        for row in resp1.rows:
            total_sessions    += int(row.metric_values[0].value or 0)
            purchase_events   += int(row.metric_values[1].value or 0)
            total_page_views  += int(row.metric_values[2].value or 0)

        # Also get overall session count (without event filter)
        req_sessions = RunReportRequest(
            property=property_id,
            date_ranges=[date_range],
            metrics=[Metric(name="sessions"), Metric(name="screenPageViews")],
        )
        resp_sessions = client.run_report(req_sessions)
        if resp_sessions.rows:
            total_sessions   = int(resp_sessions.rows[0].metric_values[0].value or 0)
            total_page_views = int(resp_sessions.rows[0].metric_values[1].value or 0)

        # Parse request 2 — direct channel
        direct_sessions = 0
        for row in resp2.rows:
            channel = row.dimension_values[0].value.lower()
            if "direct" in channel:
                direct_sessions += int(row.metric_values[0].value or 0)

        # Compute KPIs
        click_purchase_conversion = (
            round(purchase_events / total_page_views * 100, 2)
            if total_page_views else None
        )
        direct_sessions_pct = (
            round(direct_sessions / total_sessions * 100, 2)
            if total_sessions else None
        )

        return {
            "click_purchase_conversion": click_purchase_conversion,
            "direct_sessions_pct": direct_sessions_pct,
            "direct_sessions": direct_sessions,
            "total_sessions": total_sessions,
            "purchase_events": purchase_events,
            "total_page_views": total_page_views,
            "period_days": period_days,
            "connected": True,
            "error": None,
        }

    except ValueError as e:
        logger.warning(f"GA4 not configured: {e}")
        return _not_connected(str(e), period_days)
    except Exception as e:
        logger.error(f"GA4 fetch failed: {e}")
        return _not_connected(str(e), period_days)


def _not_connected(error: str, period_days: int) -> dict:
    return {
        "click_purchase_conversion": None,
        "direct_sessions_pct": None,
        "direct_sessions": None,
        "total_sessions": None,
        "purchase_events": None,
        "total_page_views": None,
        "period_days": period_days,
        "connected": False,
        "error": error,
    }
