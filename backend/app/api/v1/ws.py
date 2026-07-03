"""WebSocket endpoint: /api/v1/ws/stream"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/stream")
async def stream(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "invalid json"}))
                continue
            op = msg.get("op")
            topics = msg.get("topics", [])
            if op == "subscribe" and isinstance(topics, list):
                accepted = manager.subscribe(ws, [str(t) for t in topics])
                await ws.send_text(json.dumps({"op": "subscribed", "topics": accepted}))
            elif op == "unsubscribe" and isinstance(topics, list):
                manager.unsubscribe(ws, [str(t) for t in topics])
                await ws.send_text(json.dumps({"op": "unsubscribed", "topics": topics}))
            elif op == "ping":
                await ws.send_text(json.dumps({"op": "pong"}))
            else:
                await ws.send_text(json.dumps({"error": "unknown op"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS closed: %s", exc)
        manager.disconnect(ws)
