from secrets import token_urlsafe
from time import time

from fastapi import Depends, Header, HTTPException

# In-memory token store: token -> { user_id, role, expires_at }
# NOTE: same lifetime as the rest of the in-memory session state — tokens are
# lost on server restart. Acceptable for the current single-instance deploy.
ACTIVE_TOKENS = {}

TOKEN_TTL_HOURS = 12


def create_session_token(user_id: str, role: str = "student") -> str:
    """Issue a bearer token for the given user and store it in ACTIVE_TOKENS."""
    token = f"token_{role}_{token_urlsafe(16)}"
    ACTIVE_TOKENS[token] = {
        "user_id": user_id,
        "role": role,
        "expires_at": time() + TOKEN_TTL_HOURS * 3600,
    }
    return token


def revoke_session_token(token: str):
    """Invalidate a token immediately (e.g. logout)."""
    ACTIVE_TOKENS.pop(token, None)


def _purge_expired():
    now = time()
    for token in list(ACTIVE_TOKENS):
        if ACTIVE_TOKENS[token].get("expires_at", 0) < now:
            del ACTIVE_TOKENS[token]


def get_current_user(authorization: str = Header(None)) -> dict:
    """FastAPI dependency — validates `Authorization: Bearer <token>`.

    Returns the authenticated user dict {user_id, role, expires_at}
    or raises 401.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    return user


def require_role(*roles: str):
    """Dependency factory: require the authenticated user to hold one of `roles`.

    Usage: `user: dict = Depends(require_role("counselor"))`
    """
    def _dependency(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _dependency


def validate_token(token: str) -> dict | None:
    """Return the user record for a raw token, or None if invalid/expired.

    Used for WebSocket handshakes (query param) where Header() deps
    aren't available.
    """
    if not token:
        return None
    _purge_expired()
    return ACTIVE_TOKENS.get(token)
