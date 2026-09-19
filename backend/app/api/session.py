from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, Any
from app.services.session_manager import start_session as svc_start, get_session, list_active_sessions, record_interaction, end_session
from app.services.rule_intent import analyze_with_rules

router = APIRouter(prefix="/api/session", tags=["session"])


class SessionCreate(BaseModel):
    user_id: str | None = None


class MessagePayload(BaseModel):
    session_id: str
    sender: str
    text: str


@router.post("/start")
def start_session(payload: SessionCreate):
    # svc_start() already creates the correct sessions row (keyed by
    # session_token = sid) via session_manager. The old manual insert here
    # wrote a second, mismatched row and is unused by the frontend — removed.
    sid = svc_start(payload.user_id)
    return {"session_id": sid}


@router.post("/message")
def post_message(payload: MessagePayload):
    # Analyze user text when sender is 'user'
    analysis = None
    if payload.sender == 'user':
        analysis = analyze_with_rules(payload.text)

    record_interaction(payload.session_id, payload.sender, payload.text, analysis=analysis)
    return {"ok": True}


@router.get("/{session_id}")
def get_session_state(session_id: str):
    s = get_session(session_id)
    if not s:
        return {"error": "not_found"}
    return s


@router.get("/active")
def active_sessions():
    return list_active_sessions()


@router.post("/{session_id}/end")
def close_session(session_id: str):
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
async def session_ws(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Accept messages from counselor client and broadcast to others if needed
            await manager.broadcast(session_id, data)
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)