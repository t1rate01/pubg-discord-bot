import base64
import secrets

from fastapi import HTTPException, Request, status

from app.core.auth import verify_admin_credentials
from app.db.models import app_is_initialized


def require_basic_auth(request: Request) -> None:
    if not app_is_initialized():
        return

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth header",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not verify_admin_credentials(username, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )