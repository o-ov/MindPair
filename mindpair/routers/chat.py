from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import json
import asyncio

from database import get_db, Session as SessionModel, Message
from models import TaskSubmit, SettingsUpdate, RoleConfig
from config import DEFAULT_ROLE_PROMPT_A, DEFAULT_ROLE_PROMPT_B, set_api_keys, get_api_keys, APIKeys
from services.orchestrator import Orchestrator

router = APIRouter(prefix="/api", tags=["chat"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: int):
        if session_id in self.active_connections:
            self.active_connections[session_id] = [
                ws for ws in self.active_connections[session_id] if ws != websocket
            ]

    async def send_to_session(self, session_id: int, data: dict):
        if session_id in self.active_connections:
            for ws in self.active_connections[session_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    pass


manager = ConnectionManager()


@router.post("/settings/keys")
def update_keys(keys: APIKeys):
    set_api_keys(keys)
    return {"ok": True}


@router.get("/settings/keys/status")
def keys_status():
    keys = get_api_keys()
    return {
        "minimax": bool(keys.minimax),
        "deepseek": bool(keys.deepseek),
    }


@router.post("/settings/session/{session_id}")
def update_session_settings(session_id: int, settings: SettingsUpdate, db: Session = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if settings.config_a:
        session.config_a = settings.config_a.model_dump_json()
    if settings.config_b:
        session.config_b = settings.config_b.model_dump_json()
    db.commit()
    return {"ok": True}


@router.get("/settings/defaults")
def get_defaults():
    return {
        "config_a": {
            "name": "产品大神张小龙",
            "system_prompt": DEFAULT_ROLE_PROMPT_A,
            "model": "MiniMax-M2.7-highspeed",
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        "config_b": {
            "name": "产品大神张小龙",
            "system_prompt": DEFAULT_ROLE_PROMPT_B,
            "model": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 2048,
        },
    }


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "task":
                task = msg.get("task")
                first_mover = msg.get("first_mover", "A")

                db = next(get_db())
                session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not session:
                    await manager.send_to_session(session_id, {"type": "error", "message": "Session not found"})
                    return

                import json
                config_a = json.loads(session.config_a) if session.config_a else {}
                config_b = json.loads(session.config_b) if session.config_b else {}

                orchestrator = Orchestrator(
                    db=db,
                    session_id=session_id,
                    task=task,
                    config_a=config_a,
                    config_b=config_b,
                    first_mover=first_mover,
                    consensus_rounds=2,
                )

                await orchestrator.run(
                    lambda event: manager.send_to_session(session_id, event)
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        await manager.send_to_session(session_id, {"type": "error", "message": str(e)})
        manager.disconnect(websocket, session_id)
