"""Canal en tiempo real con la consola.

Un WebSocket es una conexión que permanece abierta, de modo que el servidor puede enviar
datos al navegador en cuanto ocurren, sin que este tenga que preguntar continuamente.
"""

import asyncio

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..hub import hub
from ..security import decode_token

router = APIRouter()


@router.websocket("/ws")
async def live(ws: WebSocket, token: str = ""):
    """Envía a la consola cada evento (telemetría, inferencias, alertas, despliegues).

    Los navegadores no permiten añadir cabeceras a un WebSocket, así que el token de sesión
    llega como parámetro de la dirección. Si no hay eventos en 20 segundos se envía un "ping"
    para que la conexión no se cierre por inactividad.
    """
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
