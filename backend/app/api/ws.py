"""WebSocket endpoint: /ws?token=<access token>."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db.models import User
from app.db.session import SessionLocal
from app.services.realtime import manager

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str = ""):
    payload = decode_token(token, "access")
    user_id = None
    if payload:
        with SessionLocal() as db:
            user = db.get(User, int(payload["sub"]))
            if user and user.is_active:
                user_id = user.id
    if user_id is None:
        await websocket.close(code=4401)
        return
    await manager.connect(user_id, websocket)
    try:
        await websocket.send_json({"event": "connected", "user_id": user_id})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
