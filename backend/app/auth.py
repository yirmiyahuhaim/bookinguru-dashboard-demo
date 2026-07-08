import os
import secrets
from fastapi import Depends, HTTPException, Header, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)

DASHBOARD_USER = os.getenv("DASHBOARD_USER", "bookinguru")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "investor2026")
AUTH_DISABLED  = os.getenv("AUTH_DISABLED", "false").lower() == "true"

# Internal-only access — protects sensitive financial fields (Cash, Runway).
# Set INTERNAL_PASS in Render env vars to a strong secret known only to the
# BookinGuru team.  Leave unset to disable the internal endpoint entirely.
INTERNAL_PASS = os.getenv("INTERNAL_PASS", "")


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if AUTH_DISABLED:
        return "demo"
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    correct_user = secrets.compare_digest(credentials.username.encode(), DASHBOARD_USER.encode())
    correct_pass = secrets.compare_digest(credentials.password.encode(), DASHBOARD_PASS.encode())
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def require_internal_auth(x_internal_token: str = Header(default="")):
    """
    Second-factor auth for sensitive internal metrics (Cash Balance, Runway).
    Clients must include the header:  X-Internal-Token: <INTERNAL_PASS>
    Returns 503 if INTERNAL_PASS is not configured on the server.
    Returns 401 if the token is wrong or missing.
    """
    if not INTERNAL_PASS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal access is not configured on this server.",
        )
    if not x_internal_token or not secrets.compare_digest(
        x_internal_token.encode(), INTERNAL_PASS.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token.",
        )
    return x_internal_token
