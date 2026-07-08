import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "419674066")


def _get_client():
    """Build a GA4 Data API client from the service account JSON env var."""
    creds_json = os.getenv("GA4_CREDENTIALS_JSON")
    if not creds_json:
        return None
    try:
        from google.oauth2 import service_account
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        return BetaAnalyticsDataClient(credentials=credentials)
    except Exception as e:
        logger.error(f"GA4 client init failed: {e}")
        return None


def get_ga4_metrics(days: int = 30) -> Dict[str, Any]:
    """
    Pull Click→Purchase Conversion and Direct Booking % from GA4.
    Returns a dict with the metrics, or {'connected': False} if not available.
    """
    client = _get_client()
    if not client:
        return {"connected": False, "reason": "GA4_CREDENTIALS_JSON not set"}

    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, Dimension, Metric, DateRange
        )

        request = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            dimensions=[Dimension(name="sessionDefaultChannelGrouping")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="ecommercePurchases"),
                Metric(name="screenPageViews"),
            ],
            date_ranges=[DateRange(
                start_date=f"{days}daysAgo",
                end_date="today"
            )],
        )
        response = client.run_report(request)

        total_sessions = 0
        total_purchases = 0
        total_pageviews = 0
        direct_sessions = 0

        for row in response.rows:
            channel = row.dimension_values[0].value
            sessions   = int(row.metric_values[0].value or 0)
            purchases  = int(row.metric_values[1].value or 0)
            pageviews  = int(row.metric_values[2].value or 0)

            total_sessions   += sessions
            total_purchases  += purchases
            total_pageviews  += pageviews

            if "direct" in channel.lower():
                direct_sessions += sessions

        # Row 25: Click → Purchase Conversion = purchases / sessions × 100
        click_to_purchase = (
            round(total_purchases / total_sessions * 100, 2)
            if total_sessions else 0.0
        )

        # Row 8 proxy: Direct Booking % = direct sessions / total sessions × 100
        direct_pct = (
            round(direct_sessions / total_sessions * 100, 2)
            if total_sessions else 0.0
        )

        return {
            "connected": True,
            "date_range_days": days,
            "total_sessions": total_sessions,
            "total_purchases": total_purchases,
            "click_to_purchase_conversion": click_to_purchase,
            "direct_session_pct": direct_pct,
            "direct_sessions": direct_sessions,
        }

    except Exception as e:
        logger.error(f"GA4 query failed: {e}")
        return {"connected": False, "reason": str(e)}
