"""Canal en tiempo real con la consola."""

import asyncio

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..hub import hub
from ..security import decode_token

router = APIRouter()


@router.websocket("/ws")
async def live(ws: WebSocket, token: str = ""):
    try:
        decode_token(token)
    except jwt.PyJWTError:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    queue = hub.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                await ws.send_json(event)
            except TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
