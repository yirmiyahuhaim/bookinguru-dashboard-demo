import re
import secrets
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AlertSubscriber
from ..auth import require_auth

router = APIRouter(prefix="/alerts", tags=["alerts"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _unsub_page(message: str, ok: bool = True) -> str:
    colour = "#059669" if ok else "#dc2626"
    return f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>BookinGuru Alerts</title></head>
    <body style="font-family:Arial,Helvetica,sans-serif;background:#f8fafc;margin:0;padding:48px 16px">
      <div style="max-width:440px;margin:auto;background:#fff;border-radius:14px;
                  box-shadow:0 4px 20px rgba(0,0,0,.06);padding:28px 26px;text-align:center">
        <div style="font-size:15px;color:{colour};font-weight:700;margin-bottom:8px">BookinGuru Alerts</div>
        <p style="font-size:14px;color:#334155;line-height:1.5;margin:0">{message}</p>
      </div>
    </body></html>"""


class SubscribeRequest(BaseModel):
    email: str


@router.post("/subscribe")
def subscribe(payload: SubscribeRequest, db: Session = Depends(get_db), _: str = Depends(require_auth)):
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    existing = db.query(AlertSubscriber).filter(AlertSubscriber.email == email).first()
    if existing:
        if not existing.active:
            existing.active = True
            db.commit()
            return {"status": "resubscribed", "email": email}
        return {"status": "already_subscribed", "email": email}
    db.add(AlertSubscriber(email=email, active=True))
    db.commit()
    return {"status": "subscribed", "email": email}


@router.post("/unsubscribe")
def unsubscribe(payload: SubscribeRequest, db: Session = Depends(get_db), _: str = Depends(require_auth)):
    email = payload.email.strip().lower()
    sub = db.query(AlertSubscriber).filter(AlertSubscriber.email == email).first()
    if sub:
        sub.active = False
        db.commit()
    return {"status": "unsubscribed", "email": email}


@router.api_route("/u", methods=["GET", "POST"], include_in_schema=False)
def public_unsubscribe(email: str = "", token: str = "", db: Session = Depends(get_db)):
    """
    One-click unsubscribe link used in alert emails — no login required. Secured
    by an HMAC token so a link only works for its own email address.
    Handles GET (human clicks the link) and POST (RFC 8058 one-click from Gmail/Outlook).
    """
    from ..services.alerts import unsub_token
    email = (email or "").strip().lower()
    if not email or not token or not secrets.compare_digest(token, unsub_token(email)):
        return HTMLResponse(_unsub_page("This unsubscribe link is invalid or has expired.", ok=False),
                            status_code=400)
    sub = db.query(AlertSubscriber).filter(AlertSubscriber.email == email).first()
    if sub and sub.active:
        sub.active = False
        db.commit()
    return HTMLResponse(_unsub_page(
        f"You’ve been unsubscribed. <b>{email}</b> will no longer receive BookinGuru alerts."))


@router.get("/subscribers")
def list_subscribers(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    subs = (
        db.query(AlertSubscriber)
          .filter(AlertSubscriber.active == True)  # noqa: E712
          .order_by(AlertSubscriber.created_at.desc())
          .all()
    )
    return [{"email": s.email, "since": s.created_at.isoformat() if s.created_at else None} for s in subs]


@router.get("/status")
def status(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    """Current metrics vs thresholds and whether email is configured (read-only)."""
    from ..services.alerts import alert_status
    return alert_status(db)


@router.post("/test-email")
def test_email(db: Session = Depends(get_db), _: str = Depends(require_auth)):
    """Send a sample alert to all subscribers to verify the Brevo setup."""
    from ..services.alerts import send_test_email
    return send_test_email(db)
