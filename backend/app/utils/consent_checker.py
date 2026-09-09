from app.database.database import supabase
from datetime import datetime
from time import time

# In-memory cache: session_id -> (consent_given, cached_at).
# Consent is recorded once per session and essentially never revoked, so a
# short TTL lets us skip repeated Supabase round-trips per message.
_CONSENT_CACHE = {}
_CONSENT_CACHE_TTL = 300

def _cached_consent(session_id: str):
    item = _CONSENT_CACHE.get(session_id)
    if item and time() - item[1] < _CONSENT_CACHE_TTL:
        return item[0]
    _CONSENT_CACHE.pop(session_id, None)
    return None


def log_consent(session_id: str, consent_given: bool):
    """
    Insert or update a consent record for a session.
    """
    _CONSENT_CACHE.pop(session_id, None)  # invalidate cache — value changed
    try:
        existing = supabase.table("consents")\
            .select("*")\
            .eq("session_id", session_id)\
            .execute()

        if existing.data:
            supabase.table("consents")\
                .update({
                    "consent_given": consent_given,
                    "updated_at": datetime.utcnow().isoformat()
                })\
                .eq("session_id", session_id)\
                .execute()
        else:
            supabase.table("consents")\
                .insert({
                    "session_id": session_id,
                    "consent_given": consent_given,
                })\
                .execute()
    except Exception as e:
        print(f"Supabase consent error: {e}")


def has_consent(session_id: str) -> bool:
    """
    Check if a session has given consent.
    Returns True only if consent was explicitly recorded as True.
    """
    cached = _cached_consent(session_id)
    if cached is not None:
        return cached

    try:
        result = supabase.table("consents")\
            .select("consent_given")\
            .eq("session_id", session_id)\
            .eq("consent_given", True)\
            .execute()

        value = len(result.data) > 0
        _CONSENT_CACHE[session_id] = (value, time())
        return value
    except Exception as e:
        print(f"Supabase consent check error: {e}")
        return False