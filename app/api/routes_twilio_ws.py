from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.transport.twilio.media_stream import parse_media_stream_message


def create_twilio_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/twilio/media/{session_id}")
    async def twilio_media_stream(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        try:
            while True:
                try:
                    text = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                parse_media_stream_message(text)
        finally:
            try:
                await websocket.close()
            except RuntimeError:
                pass

    return router
