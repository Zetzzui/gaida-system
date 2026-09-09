# backend/app/main.py
import sys
import os
from fastapi import Response



# ----------------------------
# Add project root to Python path
# ----------------------------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# ----------------------------
# Imports
# ----------------------------
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel


from app.services.intent_router import analyze_intent
from app.services.rate_limiter import check_rate_limit
from app.services.session_manager import get_session
from app.utils.auth import get_current_user
from app.api import auth
from app.api.voice import router as audio_router
from app.api.counselor import router as counselor_router
from app.api.session import router as session_router

app = FastAPI(title="GAIDA Backend")


# ----------------------------
# Pre-warm cold-start dependencies at startup
# ----------------------------
@app.on_event("startup")
def prewarm():
    # 1. Pre-load ML classifier models
    try:
        from app.services.ml_classifier import _load_all_models
        _load_all_models()
        print("[startup] ML models loaded")
    except Exception as e:
        print(f"[startup] ML model load skipped: {e}")

    # 2. Warm Supabase connection pool
    try:
        from app.database.database import supabase
        supabase.table("sessions").select("id").limit(1).execute()
        print("[startup] Supabase connection warmed")
    except Exception as e:
        print(f"[startup] Supabase warm skipped: {e}")


# ----------------------------
# Routers
# ----------------------------
app.include_router(auth.router)
app.include_router(audio_router)
app.include_router(counselor_router)
app.include_router(session_router)

# ----------------------------
# CORS
# ----------------------------
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://gaida-system.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Security headers
# ----------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ----------------------------
# Models
# ----------------------------
class UserInput(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    intent: str | None = None
    vent_mode: bool = False

# ----------------------------
# Routes
# ----------------------------

@app.head("/")
def root_head():
    return Response(status_code=200)


@app.get("/")
def root():
    return {"status": "ok", "message": "GAIDA Backend"}


@app.post("/virtual-agent")
def virtual_agent(input: UserInput, user: dict = Depends(get_current_user)):
    check_rate_limit(user["user_id"])

    if input.session_id:
        session = get_session(input.session_id)
        if session and session.get("user_id") and session["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Session does not belong to this user")

    result = analyze_intent(
        user_message=input.message,
        session_id=input.session_id,
        user_id=user["user_id"],
        vent_mode=input.vent_mode,
    )

    if result.get("counselor_active"):
        return {
            "session_id": result.get("session_id"),
            "counselor_active": True,
            "response": None,
        }

    return {
        "session_id": result.get("session_id"),
        "intent": result.get("intent"),
        "confidence": result.get("confidence"),
        "anxiety_level": result.get("anxiety_level"),
        "severity": result.get("severity"),
        "anxiety_score": result.get("anxiety_score"),
        "response": result.get("response"),
        "method": result.get("method"),
    }