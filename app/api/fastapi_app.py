from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from app.config import get_settings
from app.core.exceptions import ProviderError
from app.services.session_service import SessionService
from app.services.session_registry import SessionRegistry
from app.transport.gradio_transport import GradioTransport
from app.transport.telnyx_transport import TelnyxTransport

app = FastAPI(title="Outbound Assistant")
settings = get_settings()
registry = SessionRegistry()
transport = TelnyxTransport() if settings.enable_telnyx_transport else GradioTransport()
session_service = SessionService(transport, registry)


class StartSessionRequest(BaseModel):
    operator_instruction: str
    call_target: str = "mock-customer"


class CustomerTurnRequest(BaseModel):
    customer_message: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(request: StartSessionRequest):
    session = await session_service.create_session(request.operator_instruction, request.call_target)
    try:
        session = await session_service.start_session(session)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return session.model_dump()


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@app.post("/sessions/{session_id}/turns")
async def handle_turn(session_id: str, request: CustomerTurnRequest):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await session_service.handle_customer_turn(session, request.customer_message)
    return session.model_dump()


@app.post("/webhooks/telnyx")
async def telnyx_webhook(payload: dict):
    session = await session_service.handle_telnyx_webhook(payload)
    return {
        "received": True,
        "event_type": payload.get("data", {}).get("event_type"),
        "session_id": session.session_id if session else None,
    }


@app.websocket("/ws/telnyx")
async def telnyx_media_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected", "message": "Telnyx media websocket stub ready"})
    await websocket.close()
