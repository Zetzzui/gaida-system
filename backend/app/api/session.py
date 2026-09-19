from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from app.services.session_manager import start_session as svc_start, get_session, list_active_sessions, record_interaction, end_session
from app.services.rule_intent import analyze_with_rules
from app.utils.auth import get_current_user, validate_token

router = APIRouter(prefix="/api/session", tags=["session"])


def require_session_owner(session_id: str, user: dict):
    """403 unless the authenticated user owns the given session (or the
    session has no recorded owner). Counselors are excluded from this check."""
    session = get_session(session_id)
    if session and session.get("user_id") and session["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")


class SessionCreate(BaseModel):
    user_id: str | None = None


class MessagePayload(BaseModel):
    session_id: str
    sender: str
    text: str


class MessageFeedback(BaseModel):
    session_id: str
    message_index: int = 0
    message_text: str = ""
    rating: str


@router.post("/start")
def start_session(payload: SessionCreate, user: dict = Depends(get_current_user)):
    # svc_start() already creates the correct sessions row (keyed by
    # session_token = sid) via session_manager. The old manual insert here
    # wrote a second, mismatched row and is unused by the frontend — removed.
    sid = svc_start(payload.user_id)
    return {"session_id": sid}


@router.post("/message")
def post_message(payload: MessagePayload, user: dict = Depends(get_current_user)):
    # Analyze user text when sender is 'user'
    analysis = None
    if payload.sender == 'user':
        analysis = analyze_with_rules(payload.text)

    record_interaction(payload.session_id, payload.sender, payload.text, analysis=analysis)
    return {"ok": True}


@router.post("/feedback")
def submit_message_feedback(payload: MessageFeedback, user: dict = Depends(get_current_user)):
    """Per-message helpfulness rating (thumbs up/down) from the student.
    Degrades gracefully if the message_feedback table has not been created yet
    (run backend/training/sql/2026_09_add_message_feedback.sql in Supabase)."""
    require_session_owner(payload.session_id, user)
    if payload.rating not in ("helpful", "not_helpful"):
        raise HTTPException(status_code=400, detail="rating must be 'helpful' or 'not_helpful'")
    if payload.rating not in ("helpful", "not_helpful"):
        raise HTTPException(status_code=400, detail="rating must be 'helpful' or 'not_helpful'")
    try:
        from app.database.database import supabase
        supabase.table("message_feedback").insert({
            "session_id": payload.session_id,
            "message_index": payload.message_index,
            "message_text": payload.message_text[:500],
            "rating": payload.rating,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }).execute()
        return {"ok": True, "stored": True}
    except Exception as e:
        print(f"[session] feedback insert error: {e}")
        return {"ok": True, "stored": False, "error": str(e)}


@router.get("/{session_id}")
def get_session_state(session_id: str, user: dict = Depends(get_current_user)):
    require_session_owner(session_id, user)
    s = get_session(session_id)
    if not s:
        return {"error": "not_found"}
    return s


@router.get("/active")
def active_sessions(user: dict = Depends(get_current_user)):
    return list_active_sessions()


@router.post("/{session_id}/end")
def close_session(session_id: str, user: dict = Depends(get_current_user)):
    require_session_owner(session_id, user)
    end_session(session_id)
    return {"ok": True}


# Simple WebSocket manager for live updates (counselor connects to a session)
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)

    async def broadcast(self, session_id: str, message: dict):
        conns = self.active_connections.get(session_id, [])
        for ws in list(conns):
            try:
                await ws.send_json(message)
            except Exception:
                conns.remove(ws)


manager = ConnectionManager()

# Register session_manager subscriber to broadcast new interactions
from app.services.session_manager import subscribe


async def _broadcast_callback(session_id: str, entry: dict):
    # send the entry to all websocket clients connected to this session
    await manager.broadcast(session_id, entry)


subscribe(_broadcast_callback)

@router.websocket("/ws/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str, token: str = Query("")):
    # The frontend connects with ?token=<session_token>. Unauthenticated
    # sockets are rejected up front so anonymous browsers can't eavesdrop on
    # live sessions.
    if not validate_token(token):
        await websocket.close(code=4401)
        return
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Accept messages from counselor client and broadcast to others if needed
            await manager.broadcast(session_id, data)
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)