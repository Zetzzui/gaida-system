# backend/app/services/rate_limiter.py

import time
from fastapi import HTTPException

RATE_LIMIT = 5
TIME_WINDOW = 60
CLEANUP_INTERVAL = 300  # sweep stale sessions every 5 min

users_requests = {}
_last_cleanup = time.time()


def _cleanup_stale_sessions(current_time: float):
    """Remove session entries with no requests left in the window."""
    stale = [
        sid for sid, timestamps in users_requests.items()
        if not timestamps or current_time - timestamps[-1] >= TIME_WINDOW
    ]
    for sid in stale:
        del users_requests[sid]


def check_rate_limit(session_id: str):
    """Raises HTTPException if session exceeds rate limit."""
    global _last_cleanup
    current_time = time.time()

    if session_id not in users_requests:
        users_requests[session_id] = []

    # Remove requests older than TIME_WINDOW
    users_requests[session_id] = [
        timestamp for timestamp in users_requests[session_id]
        if current_time - timestamp < TIME_WINDOW
    ]

    if len(users_requests[session_id]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    users_requests[session_id].append(current_time)

    # Periodic sweep so idle sessions don't accumulate forever
    if current_time - _last_cleanup > CLEANUP_INTERVAL:
        _cleanup_stale_sessions(current_time)
        _last_cleanup = current_time