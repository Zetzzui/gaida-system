import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.database.database import supabase
from app.constants import TEST_CREDENTIALS
from app.services.rate_limiter import check_rate_limit
from app.utils.auth import create_session_token


ALLOWED_DOMAIN = "@ue.edu.ph"

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ForgotPasswordRequest(BaseModel):
    email: str
    role: str = "student"


class LoginRequest(BaseModel):
    student_number: str
    email: str
    access_code: str
    antibot: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    student_id: str = None
    session_token: str = None


class ConsentRequest(BaseModel):
    session_id: str
    consent_given: bool


class GoogleLoginRequest(BaseModel):
    credential: str
    role: str = "student"


def validate_email_domain(email: str) -> bool:
    return email.strip().lower().endswith(ALLOWED_DOMAIN)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """
    Authenticate student with temporary test credentials.
    Returns a session token on successful login.
    """
    check_rate_limit(payload.student_number)

    student_number = payload.student_number.strip()

    if not validate_email_domain(payload.email):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )
    
    credentials = TEST_CREDENTIALS.get(student_number)
    
    if not credentials or payload.access_code != credentials.get("access_code"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    session_token = create_session_token(student_number, role="student")

    return LoginResponse(
        success=True,
        message="Login successful",
        student_id=student_number,
        session_token=session_token,
    )


@router.post("/google", response_model=LoginResponse)
def google_login(payload: GoogleLoginRequest):
    """
    Verify a Google ID token and issue a GAIDA session token.
    Only verified @ue.edu.ph Google accounts are accepted.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on the server")

    try:
        info = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            client_id,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    if not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google email is not verified")

    email = (info.get("email") or "").strip().lower()
    if not validate_email_domain(email):
        raise HTTPException(
            status_code=401,
            detail="Only University of the East (@ue.edu.ph) accounts may sign in",
        )

    check_rate_limit(email)

    role = (payload.role.strip().lower() or "student")
    if role not in ("student", "counselor"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user_id = email
    for sid, creds in TEST_CREDENTIALS.items():
        if str(creds.get("email", "")).strip().lower() == email:
            user_id = sid
            break

    session_token = create_session_token(user_id, role=role)

    return LoginResponse(
        success=True,
        message="Login successful",
        student_id=user_id,
        session_token=session_token,
    )


@router.post("/consent")
def record_consent(payload: ConsentRequest):
    """
    Record user consent for logging interactions.
    """
    existing = supabase.table("consents")\
        .select("*")\
        .eq("session_id", payload.session_id)\
        .execute()
    
    if existing.data:
        supabase.table("consents")\
            .update({
                "consent_given": payload.consent_given,
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq("session_id", payload.session_id)\
            .execute()
    else:
        supabase.table("consents")\
            .insert({
                "session_id": payload.session_id,
                "consent_given": payload.consent_given,
            })\
            .execute()
    return {
        "success": True,
        "message": f"Consent recorded: {payload.consent_given}",
        "session_id": payload.session_id,
    }


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    """
    Initiate password reset. Always returns success to prevent email enumeration.
    """
    return {"ok": True, "message": "If the email is registered, a reset link has been sent."}




